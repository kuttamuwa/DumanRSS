"""
Duman ARGE RSS Feeder

"""
import os.path
from datetime import datetime

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import create_engine, Column, Integer, String, Sequence, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session
from telegram import Bot
from telegram.ext import Updater, CommandHandler

from config import settings

global bot

date_example = "22052022-16:00"
date_format = "%d%m%Y-%H:%M"

db = create_engine(f"sqlite:///{os.path.join(os.path.abspath('.'), 'app.db')}", echo=True,
                   connect_args={'check_same_thread': False})
session = Session(bind=db)

Base = declarative_base()

scheduler = BackgroundScheduler(daemon=True)


# bot init
def init_bot():
    # create
    bot = Bot(token=settings.token)
    updater = Updater(token=bot.token, use_context=True)
    dispatcher = updater.dispatcher

    # handlers
    help_handler = CommandHandler('help', help_cmd)
    dispatcher.add_handler(help_handler)

    get_handler = CommandHandler('get', get_messages)
    dispatcher.add_handler(get_handler)

    start_handler = CommandHandler('start', start_cmd)
    dispatcher.add_handler(start_handler)

    set_handler = CommandHandler('create', create_message)
    dispatcher.add_handler(set_handler)

    drop_handler = CommandHandler('drop', drop_tasks)
    dispatcher.add_handler(drop_handler)

    send_handler = CommandHandler('send', send_cmd)
    dispatcher.add_handler(send_handler)

    # polling
    updater.start_polling()

    return bot, updater


class TelegramActive(Base):
    __tablename__ = 'telegram_active'

    id = Column(Integer, Sequence('id_seq'), primary_key=True)
    chat_id = Column(String, unique=True)
    username = Column(String, unique=True)


class Task(Base):
    __tablename__ = 'tasks'

    id = Column(Integer, Sequence('id_seq'), primary_key=True)
    job_id = Column(String)
    run_date = Column(DateTime)
    msg = Column(String)


# environment functions
def create_user(chat_id, username):
    q = session.query(TelegramActive).filter(TelegramActive.chat_id == chat_id)
    if q.count() == 1:
        q.update(values={
            'chat_id': chat_id,
            'username': username})
    else:
        user = TelegramActive(chat_id=chat_id, username=username)
        session.add(user)

    session.commit()


def search_and_add_tasks():
    tasks = session.query(Task)

    if tasks:
        for task in tasks:
            if not scheduler.get_job(job_id=task.job_id):
                msg = task.msg
                tarih = task.run_date
                scheduler.add_job(
                    send_msg_all,
                    'date',
                    kwargs={'text': msg},
                    run_date=tarih,
                    id=task.job_id
                )


def create_environment():
    # creation
    Base.metadata.create_all(db)
    print("Table created !")

    # add default user
    create_user(chat_id=settings.default_chat_id, username=settings.default_username)
    print("Default chat id inserted !")

    # search table and add jobs
    search_and_add_tasks()

    print("ENVIRON IS OK")


# bot functions
def help_cmd(update, context):
    response = f"""
    # Select
    /get/<job id>: Get task with job id
    /get: Get all messages. 
    \n

    # Create
    /create: (only admin) create OR UPDATE messaging task. ex: /create THIS IS FIRST DATA IN FEED, {date_example} 
    \n

    # Delete
    /drop: Messages can be dropped with
    /drop/<job id>: Deletes nth message
    
    \n
    # Send
    /send: Started to send each message to everyone
    """

    update.message.reply_text(response)


# SELECT
def get_messages(update, context):
    messages = scheduler.get_jobs()

    if context.args:
        messages = [i for i in messages if i.id == context.args[-1]]

    if messages:
        messages = "\n ".join(
            [f"Message : {i.kwargs['text']} - Run time : {i.next_run_time} \n Job id : {i.id}" for i in messages])
        update.message.reply_text(messages)
    else:
        update.message.reply_text('There is no pending message ')

    print("Listed tasks")


def send_msg_all(text):
    print("SENDING TO EVERYONE ! ")
    for instance in session.query(TelegramActive):
        bot.send_message(chat_id=instance.chat_id, text=text)


def send_cmd(update, context):
    if len(context.args) < 1:
        update.message.reply_text("Please specify your message !")

    msg = context.args[-1]
    try:
        send_msg_all(msg)
    except Exception as err:
        update.message.reply_text(f"Error raised while sending messages : {err}")
    print(f"Sent msg : {msg}")


def start_cmd(update, context):
    user = update.effective_chat.username
    chat_id = update.effective_chat.id

    update.message.reply_text(
        "Hi! Welcome to Duman RSS Feeder. Started ! \n"
        "See: /help")
    create_user(
        username=user,
        chat_id=chat_id
    )
    print("Started and created/updated user")


def create_message(update, context):
    print("Creating messsage..")
    try:
        if len(context.args) < 2:
            response = "Please put minimum 2 parameters seperated with comma. One is the message and other is date "
            print(response)
        else:
            tarih = context.args[-1]
            msg = " ".join(context.args[:-1])[:-1]
            tarih = datetime.strptime(tarih, date_format)
            now = datetime.now()
            print(f"now : {now} \n"
                  f"tarih : {tarih}")

            if tarih.timestamp() < now.timestamp():
                raise ValueError("Date must be after than now !")

            else:
                print(f"Tarih : {tarih} - Now : {tarih.now()}")
                response = (f"Mesaj : {msg} \n"
                            f"Tarih: {tarih}")
                print(response)
                job = scheduler.add_job(
                    send_msg_all,
                    'date',
                    kwargs={'text': msg},
                    run_date=tarih
                )

                t = Task(
                    run_date=tarih,
                    msg=msg,
                    job_id=job.id
                )
                session.add(t)
                # commit
                session.commit()

    except Exception as err:
        response = f"Hata alındı : {err}"
        print(response)
    update.message.reply_text(response)


def drop_tasks(update, context):
    if context.args:
        job_id = context.args[-1]
        scheduler.remove_job(job_id)
        res = f"{job_id} is dropped !"
        print(res)
    else:
        scheduler.remove_all_jobs()
        session.query(Task).delete()
        res = "All tasks are dropped !"
        print(res)

    update.message.reply_text(res)


if __name__ == '__main__':
    create_environment()
    bot, updater = init_bot()

    scheduler.start()
    updater.idle()
