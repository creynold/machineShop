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

#For Flask Mail
MAIL_SERVER = 'smtp.gmail.com'
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USE_SSL = False
MAIL_USERNAME = ''
MAIL_PASSWORD = ''
DEFAULT_MAIL_SENDER = ''
MAIL_FAIL_SILENTLY = False

#Configure everything
app = Flask(__name__)
app.config.from_object(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
db = SQLAlchemy(app)
mail = Mail(app)
oid = OpenID(app)
Markdown(app)

#Create the SQLAlchemy classes for database storage
###################################################

#User class stores: email, if they're looking for a buddy, and if they're an admin
##################################################################################
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

#TimeSlot class stores: email of user who registered slot along with date/time created
#
# Note: day is an integer from 0 to 6, hour is an integer from 0 to 23
#       __str__ is necessary for some functions in the Flask app
#######################################################################################
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

# This function is used to create the admin user
#################
def add_admin():
   if User.query.filter(User.email == 'cmr289@cornell.edu').first() == None:
      user = User('Collin Reynolds','cmr289@cornell.edu',False,True)
      db.session.add(user)
      db.session.commit()
   
# This function is called every minute. If midnight is encountered, all the days
# are shifted back one.
#######################
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

# Views
#################################

@app.route('/')
def splash_page():
   if session.get('logged_in'):
      return redirect(url_for('calendar'))
   return render_template('splash.html')

# Used to confirm that buddies are around. It then removes both of them from the looking list, and adds
#  them to the schedule
########################
@app.route('/confirm')
def confirm():
   if not session.get('logged_in'):
      return redirect(url_for('login',next='confirm'))
   else:
      curHour = time.localtime().tm_hour
      lookingUsers = User.query.filter(User.looking == True).all()
      onSchedule = TimeSlot.query.filter(TimeSlot.hour == curHour,TimeSlot.day == 0).all()

      # Consider someone on the schedule as looking for a buddy 
      if len(onSchedule) == 1:
         moveUser = User.query.filter(User.email == onSchedule[0].email).first()
         lookingUsers.append(moveUser)
         moveUser.looking = True
         db.session.commit()

      # If someone tried to confirm while not looking for a buddy, flash an error message
      if session.get('username') not in [x.email for x in lookingUsers]:
         flash('You are not currently looking for a buddy')
         return redirect(url_for('calendar'))

      # If there is at least one other person looking for a buddy, send an email notifying them
      #  and remove everyone from the currently looking list
      if len(lookingUsers) > 1:
         msg = Message('Machine shop buddy found!',recipients=[x.email for x in lookingUsers if x.email != session.get('username')])
         msg.html = session.get('username')+' is available now! You will now be removed from the "currently looking" list and placed on the schedule.'
         mail.send(msg)

         for user in lookingUsers:
            user.looking = False
            if TimeSlot.query.filter(TimeSlot.email == user.email, TimeSlot.day==0, TimeSlot.hour == curHour).first() != None:
               db.session.add(TimeSlot(user.email,0,curHour))
 
         # Write to database
         db.session.commit()

         session['looking'] = False

      return redirect(url_for('calendar'))

# This function sets the current user's status to looking for a buddy
############
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

         # If there's one person on the schedule right now who is not the current user
         # add them to the list of looking users
         if len(onSchedule) == 1 and onSchedule[0].email != session.get('username'):
            tmpUsr = User.query.filter(User.email == onSchedule[0].email)
            lookingUsers.append(tmpUsr)
            
         # If there is more than one person looking for a buddy and the schedule is empty
         # then send emails
         if len(lookingUsers) != 0 and len(onSchedule) < 2:
            msg = Message('Machine shop buddy needed',recipients=[x.email for x in lookingUsers])
            msg.html = session.get('username')+' is looking for a buddy, and you have indicated you are looking as well. If you are available, please click <a href="'+url_for('confirm',_external=True)+'">here</a>'
            mail.send(msg)

      # Update the current users's status to looking and update the database
      User.query.filter(User.email==session.get('username')).first().looking = setlooking
      db.session.commit()
      session['looking'] = setlooking
   return Response(response=response)

# Let openID (google) handle the login
########################################
@app.route('/login',methods=['GET','POST'])
@oid.loginhandler
def login():
   # Get the next url, or default to the login page
   nextUrl =  request.args.get('next','login')

   # If already logged in, then redirect to the calendar
   if session.get('logged_in'):
      return redirect(url_for('calendar'))

   error = None
   
   # Use google for the openID login
   if request.method == 'POST':
      openid = request.form.get('openid')
      if openid:
         return oid.try_login(COMMON_PROVIDERS['google'], ask_for=['email', 'fullname', 'nickname'])
      
   return render_template('login.html', next=url_for(str(nextUrl)), error=oid.fetch_error())

# This is called after the openID login is finished
##################
@oid.after_login
def oidlogin(resp):
   # Make sure the user is in the database, otherwise flash an error message
   currentUser = User.query.filter(User.email == resp.email).first()
   if currentUser == None:
      flash('Error: You do not have access to the scheduler, please email Nathan Ellis (nie1@cornell.edu) to be added')
      return redirect(url_for('logout'))

   # Set the session variables
   session['openid'] = resp.identity_url
   session['logged_in'] = True
   session['username'] = resp.email
   session['looking'] = currentUser.looking
   session['is_admin'] = currentUser.is_admin

   return redirect(oid.get_next_url())

# This function is used to add users to the database
######################
@app.route('/saveusers',methods=['POST'])
def saveusers():
   # Make sure the current user has admin privileges
   if session.get('is_admin'):

      # Get users from the text area on the page
      textarea = [str(x) for x in request.form.get('toadd').split()]

      # Get the current users in the database
      userlist = [x.email for x in User.query.all()]

      # Add users not currently in the database
      for toadd in textarea:
         if toadd not in userlist:
            db.session.add(User(None,toadd,False,False))

      # Remove users in the database not in the text area
      for toremove in userlist:
         if toremove not in textarea:
            db.session.delete(User.query.filter(User.email==toremove).first())

      # Write database
      db.session.commit()

      return redirect(url_for('admin'))
   else:
      abort(403)

# This shows the admin page
################3
@app.route('/admin')
def admin():
   if session.get('is_admin'):
      allusers = User.query.all()
      torender = ""

      # Populate the textarea with the current users in the database
      for user in allusers:
         torender += user.email + '\n'

      return render_template('admin.html',currentlist=torender)
   else:
      abort(403)

# Logout page
######################
@app.route('/logout')
def logout():
   session.pop('logged_in', None)
   session.pop('username', None)
   session.pop('looking', None)
   session.pop('is_admin', None)
   session.pop('openid', None)
   return redirect(url_for('login'))

# The calendar page
##################
@app.route('/calendar')
def calendar():
   if not session.get('logged_in'):
      return redirect(url_for('login'))

   # Color cells for current user/other users differently
   times = {}
   mytimes = {}

   # Get the current schedule from the database and populate the dicts above
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
         
   # This sets variables used to populate the html for the calendar
   days = []
   hours = []

   # Format the hours nicely
   for x in xrange(0,24):
      tmp = time.strptime(str(x),"%H")
      tmpstr = time.strftime("%I",tmp)
      tmpstr = int(tmpstr)
      tmpstr = str(tmpstr) + time.strftime("%p",tmp).lower()
      hours.append(tmpstr)

   # Format the dates nicely
   for x in xrange(0,7):
      days.append(time.strftime('%a %m/%d',time.localtime(time.time()+x*24*3600)))

   return render_template('calendar.html',days = days,hours = hours,times=times,mytimes=mytimes,fullname=session.get('username'),looking=session.get('looking'),admin=session.get('is_admin'))

# This function saves the schedule
@app.route('/saveTimes', methods=['POST'])
def saveTimes():
   if not session.get('logged_in'):
      redirect(url_for('login'))

   addTimes = request.form['time'].split(',')
   removeTimes = request.form['remove'].split(',')

   # Count the number added/removed for debugging purposes
   numadd = 0
   numremove = 0

   # Add times to the database
   for addTime in addTimes:
      if addTime != "":
         # Parse time given by page
         addDay = int(addTime[:1])
         addHour = int(addTime[2:])

         # If the current user is adding the current time slot, check if someone else is looking
         # for a buddy either with the "need a buddy" button or if they've selected the same slot
         onSchedule = [x.email for x in TimeSlot.query.filter(TimeSlot.day == addDay,TimeSlot.hour == addHour).all()]
 
         # Add the current user to the schedule
         db.session.add(TimeSlot(session.get('username'),addDay,addHour))
         numadd += 1

         # Check if there's someone else looking here if this slot is the current time
         if len(onSchedule) == 1 and not session.get('looking') and str(time.localtime().tm_hour) == str(addHour) and addDay == 0:
            msg = Message('Machine shop buddy found!',recipients=onSchedule)
            msg.html = session.get('username')+' is available now!'
            mail.send(msg)

   # Remove times from database
   for removeTime in removeTimes:
      if removeTime != "":
         # Parse time
         removeDay = int(removeTime[:1])
         removeHour = int(removeTime[2:])

         # Delete from database
         db.session.delete(TimeSlot.query.filter(TimeSlot.email==session.get('username'),TimeSlot.day == removeDay, TimeSlot.hour == removeHour).first())
         numremove += 1

   # Write database
   db.session.commit()
   return Response(response="Successfully added {0} times and removed {1} times".format(numadd,numremove))

if __name__ == '__main__':
   app.run()
