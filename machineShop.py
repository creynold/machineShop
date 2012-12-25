###########################################
# The LASSP Graduate Machine Shop Scheduler
#
# Author: Collin Reynolds
#   Date: December 24, 2012
#
###########################################
import sqlite3
from flaskext.markdown import Markdown
from contextlib import closing
from flask import Flask, request, session, g, redirect, url_for, \
     abort, render_template, flash, Response
from flask_mail import Mail, Message
from uwsgidecorators import *
from flask_openid import OpenID
from flask_openid import COMMON_PROVIDERS
import time

# configuration
DATABASE = '/tmp/flaskr.db'
DEBUG = True
SECRET_KEY = '\xd1<Ep\xfd\x9a\xc3\xce~\x82\x95\x87M\xab\xa9,i\xf5\xb3\t\x81z\x1e\x1b'
MAIL_SERVER = 'smtp.gmail.com'
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USE_SSL = False
MAIL_USERNAME = 'lasspgradmachineshop'
MAIL_PASSWORD = 'let metal fly'
DEFAULT_MAIL_SENDER = 'LASSP Graduate Machine Shop'
MAIL_FAIL_SILENTLY = False

app = Flask(__name__)
app.config.from_object(__name__)
mail = Mail(app)
oid = OpenID(app,'/tmp')
Markdown(app)

def connect_db():
   return sqlite3.connect(app.config['DATABASE'])

def init_db():
   with closing(connect_db()) as db:
      with app.open_resource('schema.sql') as f:
         db.cursor().executescript(f.read())
      db.commit()

def add_admin():
   db = sqlite3.connect(app.config['DATABASE'])
   db.execute('insert into users (username,looking,is_admin) values (?, ?, ?)',['cmr289@cornell.edu',False,True])
   db.commit()
   

def query_db(query, args=(), one=False):
   cur = g.db.execute(query, args)
   rv = [dict((cur.description[idx][0], value)
           for idx, value in enumerate(row)) for row in cur.fetchall()]
   return (rv[0] if rv else None) if one else rv

def query_db_local(db, query, args=(), one=False):
   cur = db.execute(query, args)
   rv = [dict((cur.description[idx][0], value)
           for idx, value in enumerate(row)) for row in cur.fetchall()]
   return (rv[0] if rv else None) if one else rv

@timer(60)
def oneminute(num):
   db = connect_db()

   if time.localtime().tm_hour == 0 and time.localtime().tm_min == 0:
      curSched = query_db_local(db,'select * from schedule')
      updSched = []
      for slot in curSched:
         tmpTime = slot['time']
         newTime = str(int(slot['time'][:1])-1) + tmpTime[1:]
         if str(newTime[:1]) >= 0:
            db.execute('update schedule set time=? where time=? and username=?',[newTime,tmpTime,slot['username']]) 
         else:
            db.execute('delete from schedule where time=? and username=?',[tmpTime,slot['username']])
   
      db.commit()
   db.close()

@app.before_request
def before_request():
   g.db = connect_db()

@app.teardown_request
def teardown_request(exception):
   g.db.close()

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
      curtimeslot = "0-" + str(time.localtime().tm_hour)
      lookingUsers = [x['username'] for x in query_db('select username from users where looking=?',[True])]
      onSchedule = [x['username'] for x in query_db('select username from schedule where time=?',[curtimeslot])]

      if len(onSchedule) == 1:
         lookingUsers.append(onSchedule[0])

      if session.get('username') not in lookingUsers:
         flash('You are not currently looking for a buddy')
         return redirect(url_for('calendar'))
      if len(lookingUsers) > 1:
         msg = Message('Machine shop buddy found!',recipients=[x for x in lookingUsers if x != session.get('username')])
         msg.html = session.get('username')+' is available now! You will be now removed from the "currently looking" list and placed on the schedule.'
         mail.send(msg)

         g.db.execute('update users set looking=? where username=?',[False,session.get('username')])
         g.db.execute('insert into schedule (username,time) values (?, ?)',[session.get('username'),curtimeslot])
         lookingUsers.remove(session.get('username'))
         lookingUsers.remove(onSchedule[0])
         for user in lookingUsers:
            g.db.execute('update users set looking=? where username=?',[False,user])
            g.db.execute('insert into schedule (username,time) values (?, ?)',[user,curtimeslot])
         g.db.commit()
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
         curtimeslot = "0-" + str(time.localtime().tm_hour)
         onSchedule = [x['username'] for x in query_db('select username from schedule where time=?',[curtimeslot])]

         setlooking = True
         response = "don't need buddy now"

         lookingUsers = [x['username'] for x in query_db('select username from users where looking=?',[True])]

         if len(onSchedule) == 1:
            lookingUsers.append(onSchedule[0])

         if len(lookingUsers) != 0:
            msg = Message('Machine shop buddy needed',recipients=lookingUsers)
            msg.html = session.get('username')+' is looking for a buddy, and you have indicated you are looking as well. If you are available, please click <a href="'+url_for('confirm',_external=True)+'">here</a>'
            mail.send(msg)

      g.db.execute('update users set looking=? where username=?',[setlooking,session.get('username')])
      g.db.commit()
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
      
   #return render_template('login.html', next=oid.get_next_url(), error=oid.fetch_error())
   return render_template('login.html', next=url_for(str(nextUrl)), error=oid.fetch_error())

@oid.after_login
def oidlogin(resp):
   if query_db('select username from users where username=?',[resp.email],one=True) == None:
      flash('Error: You do not have access to the scheduler, please email Nathan Ellis (nie1@cornell.edu) to be added')
      return redirect(url_for('logout'))
   session['openid'] = resp.identity_url
   #if resp.email[-12:] != '@cornell.edu':
   #   flash('Not a valid cornell email address')
   #   return redirect(url_for('logout'))
   session['logged_in'] = True
   session['username'] = resp.email
   session['looking'] = query_db('select looking from users where username=?',[resp.email],one=True)['looking']
   session['is_admin'] = query_db('select is_admin from users where username=?',[resp.email],one=True)['is_admin']
   return redirect(oid.get_next_url())

@app.route('/saveusers',methods=['POST'])
def saveusers():
   if session.get('is_admin'):
      textarea = [str(x) for x in request.form.get('toadd').split()]
      userlist = [x['username'] for x in query_db('select username from users',[])]
      for toadd in textarea:
         if toadd not in userlist:
            g.db.execute('insert into users (username,looking,is_admin) values (?, ?, ?)',[toadd,False,False])
      for toremove in userlist:
         if toremove not in textarea:
            g.db.execute('delete from users where username=?',[toremove])
      g.db.commit()
      return redirect(url_for('admin'))
   else:
      abort(403)

@app.route('/admin')
def admin():
   if session.get('is_admin'):
      allusers = query_db('select username from users',[])
      torender = ""
      for user in allusers:
         torender += user['username'] + '\n'
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
   for entry in query_db('select * from schedule',[]):
      if str(entry['username']) == session.get('username'):
         if str(entry['time']) in mytimes:
            mytimes[str(entry['time'])].append(str(entry['username']))
         else:
            mytimes[str(entry['time'])] = [str(entry['username'])]
      else:
         if str(entry['time']) in times:
            times[str(entry['time'])].append(str(entry['username']))
         else:
            times[str(entry['time'])] = [str(entry['username'])]
         
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
         onSchedule = [x['username'] for x in query_db('select username from schedule where time=?',[addTime])]
         g.db.execute('insert into schedule (username,time) values (?, ?)',[session.get('username'),addTime])
         numadd += 1
         if str(time.localtime().tm_hour) == addTime[2:] and len(onSchedule) == 1:
            msg = Message('Machine shop buddy found!',recipients=onSchedule)
            msg.html = session.get('username')+' is available now!'
            mail.send(msg)
   for removeTime in removeTimes:
      if removeTime != "":
         g.db.execute('delete from schedule where username=? and time=?',[session.get('username'),removeTime])
         numremove += 1
   g.db.commit()
   return Response(response="Successfully added {0} times and removed {1} times".format(numadd,numremove))
   #return Response(response=query_db('select * from schedule where username = ?',[session.get('username')]))

init_db()
add_admin()

if __name__ == '__main__':
   init_db()
   add_admin()
   app.run()
