###########################################
# The LASSP Graduate Machine Shop Scheduler
#
# Author: Collin Reynolds
#   Date: December 24, 2012
#
###########################################
from flask.ext.sqlalchemy import SQLAlchemy
from flaskext.markdown import Markdown
from contextlib import closing
from flask import Flask, request, session, g, redirect, url_for, \
     abort, render_template, flash, Response
from flask_mail import Mail, Message
from uwsgidecorators import *
from flask_openid import OpenID
from flask_openid import COMMON_PROVIDERS
import time 
import os

# configuration
DEBUG = True
SECRET_KEY = ''
MAIL_SERVER = 'smtp.gmail.com'
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USE_SSL = False
MAIL_USERNAME = ''
MAIL_PASSWORD = ''
DEFAULT_MAIL_SENDER = ''
MAIL_FAIL_SILENTLY = False

app = Flask(__name__)
app.config.from_object(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
db = SQLAlchemy(app)
mail = Mail(app)
oid = OpenID(app)
Markdown(app)

class User(db.Model):
   __tablename__ = 'users'
   id = db.Column(db.Integer,primary_key=True)
   email = db.Column(db.String(120),unique=True)
   name = db.Column(db.String(120),unique=True)
   looking = db.Column(db.Boolean)
   is_admin = db.Column(db.Boolean)

   def __init__(self, name=None, email=None, looking=False, is_admin=False):
      self.name = name
      self.email = email
      self.looking = looking
      self.is_admin = is_admin

   def __repr__(self):
      return '<User %r>' % (self.email)

class TimeSlot(db.Model):
   __tablename__ = 'schedule'
   id = db.Column(db.Integer,primary_key=True)
   email = db.Column(db.String(120))
   day = db.Column(db.Integer)
   hour = db.Column(db.Integer)

   def __init__(self, email, day, hour):
      self.email = email
      self.day = day
      self.hour = hour

   def __repr__(self):
      return '%d-%d' % (self.day,self.hour)

   def __str__(self):
      return '%d-%d' % (self.day,self.hour)

def init_db():
   db.create_all()

def add_admin():
   if User.query.filter(User.email == 'cmr289@cornell.edu').first() == None:
      user = User('Collin Reynolds','cmr289@cornell.edu',False,True)
      db.session.add(user)
      db.session.commit()
   
@timer(60)
def oneminute(num):
   if time.localtime().tm_hour == 0 and time.localtime().tm_min == 0:
      curSched = TimeSlot.query.all()
      updSched = []
      for slot in curSched:
         if slot.day > 0:
            slot.day = slot.day - 1
         else:
            db.session.delete(slot)
   
   db.session.commit()

@app.route('/')
def splash_page():
   if session.get('logged_in'):
      return redirect(url_for('calendar'))
   return render_template('splash.html')

@app.route('/confirm')
def confirm():
   if not session.get('logged_in'):
      return redirect(url_for('login',next='confirm'))
   else:
      curHour = time.localtime().tm_hour
      lookingUsers = User.query.filter(User.looking == True).all()
      onSchedule = TimeSlot.query.filter(TimeSlot.hour == curHour,TimeSlot.day == 0).all()

      if len(onSchedule) == 1:
         moveUser = User.query.filter(User.email == onSchedule[0].email).first()
         lookingUsers.append(moveUser)
         moveUser.looking = True
         db.session.commit()

      if session.get('username') not in [x.email for x in lookingUsers]:
         flash('You are not currently looking for a buddy')
         return redirect(url_for('calendar'))
      if len(lookingUsers) > 1:
         msg = Message('Machine shop buddy found!',recipients=[x.email for x in lookingUsers if x.email != session.get('username')])
         msg.html = session.get('username')+' is available now! You will now be removed from the "currently looking" list and placed on the schedule.'
         mail.send(msg)

         for user in lookingUsers:
            user.looking = False
            if TimeSlot.query.filter(TimeSlot.email == user.email, TimeSlot.day==0, TimeSlot.hour == curHour).first() != None:
               db.session.add(TimeSlot(user.email,0,curHour))
         db.session.commit()
         session['looking'] = False
      return redirect(url_for('calendar'))

@app.route('/lookingnow',methods=['POST'])
def lookingnow():
   if not session.get('logged_in'):
      return redirect(url_for('login'))
   elif request.method == 'POST':
      response = "need buddy now"
      setlooking = False

      if request.form.get('todo') == 'looking':
         curHour = time.localtime().tm_hour
         onSchedule = TimeSlot.query.filter(TimeSlot.hour == curHour, TimeSlot.day == 0).all()

         setlooking = True
         response = "don't need buddy now"

         lookingUsers = User.query.filter(User.looking == True).all()

         if len(onSchedule) == 1 and onSchedule[0].email != session.get('username'):
            tmpUsr = User.query.filter(User.email == onSchedule[0].email)
            if not tmpUsr.looking:
               tmpUsr.looking = False
               db.session.commit()
            lookingUsers.append(tmpUsr)
            
         if len(lookingUsers) != 0 and len(onSchedule) < 2:
            msg = Message('Machine shop buddy needed',recipients=[x.email for x in lookingUsers])
            msg.html = session.get('username')+' is looking for a buddy, and you have indicated you are looking as well. If you are available, please click <a href="'+url_for('confirm',_external=True)+'">here</a>'
            mail.send(msg)

      User.query.filter(User.email==session.get('username')).first().looking = setlooking
      db.session.commit()
      session['looking'] = setlooking
   return Response(response=response)

@app.route('/login',methods=['GET','POST'])
@oid.loginhandler
def login():
   nextUrl =  request.args.get('next','login')
   if session.get('logged_in'):
      return redirect(url_for('calendar'))
   error = None
   if request.method == 'POST':
      openid = request.form.get('openid')
      if openid:
         return oid.try_login(COMMON_PROVIDERS['google'], ask_for=['email', 'fullname', 'nickname'])
      
   return render_template('login.html', next=url_for(str(nextUrl)), error=oid.fetch_error())

@oid.after_login
def oidlogin(resp):
   currentUser = User.query.filter(User.email == resp.email).first()
   if currentUser == None:
      flash('Error: You do not have access to the scheduler, please email Nathan Ellis (nie1@cornell.edu) to be added')
      return redirect(url_for('logout'))
   session['openid'] = resp.identity_url
   session['logged_in'] = True
   session['username'] = resp.email
   session['looking'] = currentUser.looking
   session['is_admin'] = currentUser.is_admin
   return redirect(oid.get_next_url())

@app.route('/saveusers',methods=['POST'])
def saveusers():
   if session.get('is_admin'):
      textarea = [str(x) for x in request.form.get('toadd').split()]
      userlist = [x.email for x in User.query.all()]
      for toadd in textarea:
         if toadd not in userlist:
            db.session.add(User(None,toadd,False,False))
      for toremove in userlist:
         if toremove not in textarea:
            db.session.delete(User.query.filter(User.email==toremove).first())
      db.session.commit()
      return redirect(url_for('admin'))
   else:
      abort(403)

@app.route('/admin')
def admin():
   if session.get('is_admin'):
      allusers = User.query.all()
      torender = ""
      for user in allusers:
         torender += user.email + '\n'
      return render_template('admin.html',currentlist=torender)
   else:
      abort(403)

@app.route('/logout')
def logout():
   session.pop('logged_in', None)
   session.pop('username', None)
   session.pop('looking', None)
   session.pop('is_admin', None)
   return redirect(url_for('login'))

@app.route('/calendar')
def calendar():
   if not session.get('logged_in'):
      return redirect(url_for('login'))

   times = {}
   mytimes = {}
   for entry in TimeSlot.query.all():
      if entry.email == session.get('username'):
         if str(entry) in mytimes:
            mytimes[str(entry)].append(str(entry.email))
         else:
            mytimes[str(entry)] = [str(entry.email)]
      else:
         if str(entry) in times:
            times[str(entry)].append(str(entry.email))
         else:
            times[str(entry)] = [str(entry.email)]
         
   days = []
   hours = []
   for x in xrange(0,24):
      tmp = time.strptime(str(x),"%H")
      tmpstr = time.strftime("%I",tmp)
      tmpstr = int(tmpstr)
      tmpstr = str(tmpstr) + time.strftime("%p",tmp).lower()
      hours.append(tmpstr)
   for x in xrange(0,7):
      days.append(time.strftime('%a %m/%d',time.localtime(time.time()+x*24*3600)))
   return render_template('calendar.html',days = days,hours = hours,times=times,mytimes=mytimes,fullname=session.get('username'),looking=session.get('looking'),admin=session.get('is_admin'))

@app.route('/saveTimes', methods=['POST'])
def saveTimes():
   addTimes = request.form['time'].split(',')
   removeTimes = request.form['remove'].split(',')

   numadd = 0
   numremove = 0

   for addTime in addTimes:
      if addTime != "":
         addDay = int(addTime[:1])
         addHour = int(addTime[2:])
         onSchedule = [x.email for x in TimeSlot.query.filter(TimeSlot.day == addDay,TimeSlot.hour == addHour).all()]
         db.session.add(TimeSlot(session.get('username'),addDay,addHour))
         numadd += 1
         if len(onSchedule) == 1 and not session.get('looking') and str(time.localtime().tm_hour) == str(addHour) and addDay == 0:
            msg = Message('Machine shop buddy found!',recipients=onSchedule)
            msg.html = session.get('username')+' is available now!'
            mail.send(msg)
   for removeTime in removeTimes:
      if removeTime != "":
         removeDay = int(removeTime[:1])
         removeHour = int(removeTime[2:])
         db.session.delete(TimeSlot.query.filter(TimeSlot.email==session.get('username'),TimeSlot.day == removeDay, TimeSlot.hour == removeHour).first())
         numremove += 1
   db.session.commit()
   return Response(response="Successfully added {0} times and removed {1} times".format(numadd,numremove))

if __name__ == '__main__':
   app.run()
