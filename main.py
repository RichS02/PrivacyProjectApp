import logging
import project_constants
from pathlib import Path
import os, errno
#todo: __name__ main check
HOME_PATH = project_constants.HOME_PATH
try:
    os.makedirs(HOME_PATH)
except OSError as e:
    if e.errno != errno.EEXIST:
        raise ValueError('Failed to create home directory. Error code: '+str(e.errno))

logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p', filename=HOME_PATH+'/system.log',level=logging.WARNING)

import threading

refresh_lock = threading.Lock()
survey_lock = threading.Lock()
log_ignore_lock = threading.Lock()
log_ignore = False
def log(mes):
    # Because even after shutting down the logger, it still will write and try to create a file.
    with log_ignore_lock:
        if log_ignore:
            return
    print(str(mes))
    logging.warning(str(mes))

log("- - - - SYSTEM STARTING - - - -")

# Set the current working directory for python http server socket for front end.
#os.chdir(HOME_PATH) # Note it makes the open browser sub process also use cwd which blocks uninstall


# This is used for pyinstaller. We need to return a special path to application.
def get_app_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    else:
        return os.path.dirname(os.path.abspath(__file__))



from shutil import copyfile
import sqlite3
from urllib import parse
import pickle
import os
import blacklists
import time
import random
import utils
import copy
import http.server
import socketserver
from res.newspaper import Article
from entity_sentiment_analyzer import EntitySentimentAnalyzer
import threading
from singleton import *
import webbrowser
from tkinter import *
from tkinter import messagebox
import sys
import traceback
import datetime
import frontend
import csv
from res.langdetect import detect
from hashlib import sha256
import shutil
import json
import atexit

#Clean exit.
def exit_handler():
    log('- - - - - - EXIT_HANDLER CALLED - - - - - -')
    with refresh_lock:
        save()
atexit.register(exit_handler)

log("Imports finished.")

CHROME_HISTORY_SQLITE_FILE = "history"
HISTORY_COPY = HOME_PATH+"/history.db"
USER_DATA = HOME_PATH+"/user-data.bin"
INDEX = HOME_PATH+"/index.html"
SURVEY = HOME_PATH+"/survey.html"
ROW_URL = 0
NEUTRAL_THRESHOLD_UPPER = 0.114
NEUTRAL_THRESHOLD_LOWER = -0.062
last_reminder_time = None
user_survey_week = 1
userData = None
old_time = None
last_process_time = None
is_sleeping = False
count = 0
gray_list = []
persons_dict = {}
start_date = None
reset_user_data = False #Used to set when changing versions and want to wipe data.

html_index = ''
html_survey = ''

template_index = ''
template_survey = ''
template_thanks = ''

MAC_USER_AGENT_PATH = str(Path.home())+'/Library/LaunchAgents'
MAC_USER_AGENT_ID = 'com.stony-brook.nlp.privacy-project-agent'
MAC_AGENT_XML = '<?xml version="1.0" encoding="UTF-8"?>\
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\
<plist version="1.0">\
<dict>\
<key>Label</key>\
<string>'+MAC_USER_AGENT_ID+'</string>\
<key>Program</key>\
<string>'+HOME_PATH+"/autorun.sh"+'</string>\
<key>RunAtLoad</key>\
<true/>\
<key>KeepAlive</key>\
<false/>\
</dict>\
</plist>'

MAC_AUTORUN_SCRIPT = '#!/bin/sh\nopen -a "privacy-project-V'+str(project_constants.VERSION_NUM)+'.app"'

class UserDataEntity:
    def __init__(self, name):
        self.name = name
        self.labels = [] #-1 neg , 0 neu, 1 pos
        self.links = [] #Aligns with labels.
        self.dbpedia_data = None # [id, name, desc]


    def getAvgLabelScore(self):
        return sum(self.labels)/float(len(self.labels))

    def getFrequency(self):
        return len(self.labels)


class UserDataURL:
    def __init__(self, url, processed, gray, timeVisited):
        self.url = url
        self.processed = processed
        self.hash = None  # Duplication detection-Some links might refer to the same article. In this case we ignore it.
        self.timeVisited = timeVisited
        self.gray = gray


class UserData:
    def __init__(self):
        self.urls = {}
        self.entities = {}
        self.survey_week = 1  # When get_survey_week() is > survey_week then prompt user to submit survey.


class MyRequestHandler(http.server.SimpleHTTPRequestHandler):
    #We don't use CWD because it causes issues on windows when opening a browser because the sub process inherits CWD and then fails to uninstall that directory. Could also fix by modifying the browser sub process but this is easier.
    def translate_path(self, path):
        #path = http.server.SimpleHTTPRequestHandler.translate_path(self, path)
        if path.startswith('http'):
            return path # Don't modify paths for http. Used for the google form.
        return HOME_PATH+path if path != '/thanks.html' else get_app_path()+'/res'+path

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        http.server.SimpleHTTPRequestHandler.end_headers(self)

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

    def do_GET(self):
        with refresh_lock:
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            if self.path == '/survey.html':
                updateFrontend2()
                self.wfile.write(html_survey.encode('utf-8',errors="ignore"))
            elif self.path == '/thanks.html':
                self.wfile.write(template_thanks.encode('utf-8', errors="ignore"))
            else:
                updateFrontend()
                self.wfile.write(html_index.encode('utf-8', errors="ignore"))

    #def do_GET(self):
    #
    #    if self.path == '/':
    #        self.path = '/index.html'
    #    return http.server.SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):

        len = int(self.headers.get('Content-Length'))
        body = self.rfile.read(len).decode('utf8',errors="ignore")

        if 'uninstall' in body:
            log("Uninstalling")
            self.path = '/thanks.html'
            self.do_GET()
            thread3 = threading.Thread(target=uninstall)
            thread3.daemon = True
            thread3.start()
            return
        elif 'results=' in body:
            log("User submitting survey.")
            results = body.replace('results=','')
            full_path = project_constants.GOOGLE_FORM_FILL_PATH+results
            self.send_response(301) # Redirect
            self.send_header('Location', full_path)
            self.end_headers()
            with refresh_lock:
                with survey_lock:
                    global user_survey_week
                    user_survey_week = get_survey_week()
                save()
            return

# Handles uninstalling safely.
def uninstall():
    time.sleep(4) #Give some time for the request.
    with log_ignore_lock:
        global log_ignore
        log_ignore = True
    with refresh_lock:
        #try:
        #    os.chdir(Path.home())  # Important, can't rmdir cwd on windows.
        #except:
        #    pass

        files = ["/.DS_Store","/version","/user-data.bin","/history.db","/system.log"]

        if os.name != 'nt':
            files.append("/autorun.sh")

        try:
            logging.shutdown()  # Closes the system.log
        except:
            pass

        for file in files:
            try:
                os.remove(HOME_PATH + file)
            except:
                pass

        #Remove newspaper subfolder.
        try:
            shutil.rmtree(HOME_PATH+"/.newspaper_scraper")
        except:
            pass

        try:
            os.rmdir(HOME_PATH)
        except:
            pass

        try:
            if os.name != 'nt':
                os.remove(MAC_USER_AGENT_PATH + '/' + MAC_USER_AGENT_ID + '.plist')
            else:
                os.remove(str(Path.home())+'\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\privacy-project.lnk')
        except:
            pass

        os._exit(0)


def getLast(str):
    parts = str.split(' ')
    if len(parts) < 2:
        return ''
    return parts[-1]

def getMergedEntities():
    uEntities = copy.deepcopy(list(userData.entities.values()))
    uEntitiesCopy = copy.deepcopy(uEntities) #copy to prevent double counting merges. todo Though this could be fixed by limiting merges.
    entitiesToRemove = []
    final = [] # [entity,boost] (2x weight to entity frequency if in gray list so it has greater chance of appearing in top 30)
    for i in range(0,len(uEntitiesCopy)):
        #continue
        match = False
        for j in range(0, len(uEntitiesCopy)):
            if uEntitiesCopy[i].name == uEntitiesCopy[j]:
                continue
            if uEntitiesCopy[j].dbpedia_data is None: #Check against dbpedia entities only.
                continue

            splitNamei = uEntitiesCopy[i].name.split()
            splitNamej = uEntitiesCopy[j].dbpedia_data[1].split() #Full entity name.

            #maybe merge based on highest freq
            if len(splitNamei) == 1 and len(splitNamej) > 1 and splitNamei[0].strip().lower() == splitNamej[-1].strip().lower(): #and uEntitiesCopy[j].getFrequency() >= uEntitiesCopy[i].getFrequency():
                uEntities[j].labels += uEntities[i].labels
                uEntities[j].links += uEntities[i].links
                #print("MERGED: "+uEntitiesCopy[i].name+" to "+uEntities[j].name)
                match = True



        if match:
            entitiesToRemove.append(uEntitiesCopy[i].name)


    for e in uEntities:
        if e.name not in entitiesToRemove and e.dbpedia_data is not None: #filter entities with db_data
            final.append([e,0])
        #else:
            #print("Ignoring "+e.name)

    #Apply the gray list to boost frequencies of more trusted entities. Note this does not impact the score in any way.
    #It simply gives a greater chance to appear in the top 30.
    for e_b in final:
        for link in e_b[0].links:
            if userData.urls[link.lower()].gray:
                e_b[1] += 1 #For each gray link, increase the frequency by 1. Means that gray links weighted X2.

    return sorted(final, key=lambda x: x[0].getFrequency()+x[1], reverse=True)[:30]


def get_survey_week():
    now = datetime.datetime.now()
    start = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    delta = now - start
    step = delta.days // 7 + 1
    if step > (project_constants.STUDY_DURATION+1): #4 weeks pass
        step = (project_constants.STUDY_DURATION+1)
    return step

def getNextSurveyDate():
    now = datetime.datetime.now()
    start = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    delta = now - start
    step = delta.days//7 + 1
    if step >= (project_constants.STUDY_DURATION+1): #4 weeks pass
        return None
    addition = datetime.timedelta(days=7*step)
    final = start+addition
    return final.strftime("%b %d, %Y")

def getLastSurveyDate():
    now = datetime.datetime.now()
    start = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    delta = now - start
    step = delta.days//7 + 1
    if step == 1:
        return None
    if step > (project_constants.STUDY_DURATION+1):
        step = (project_constants.STUDY_DURATION+1) #cap to last week
    addition = datetime.timedelta(days=7*(step-1))
    final = start+addition
    return final.strftime("%b %d, %Y")

def updateFrontend():
    log("Update frontend.")
    global count, html_index
    p_processed = 0
    p_urls = userData.urls.values()
    for p_url in p_urls:
        if (p_url.processed):
            p_processed += 1




    htmlString = template_index
    #todo: optimize
    nextSurvDateStr = getNextSurveyDate()
    #lastSurvDateStr = getLastSurveyDate()

    dateString2 = 'You have no more surveys remaining. You may now uninstall the user study'
    if nextSurvDateStr is not None:
        dateString2 = 'Please complete your next survey on or after '+nextSurvDateStr
    if survey_due():
        dateString2 = 'You have a survey due!<br>'

    dateString = '<br>'+dateString2
    htmlString = htmlString.replace("$TOP_ALERT",frontend.top_alert() if survey_due() else '')
    htmlString = htmlString.replace("$DATE", dateString)
    htmlString = htmlString.replace("$STATUS", "Sleeping" if is_sleeping else "Processing")
    htmlString = htmlString.replace("$CURRENT_ARTICLES", str(count)+"/"+str(project_constants.CAP))
    htmlString = htmlString.replace("$TOTAL_ARTICLES", str(p_processed) + "/" + str(len(p_urls)))
    htmlString = htmlString.replace("$LAST_TIME", str(last_process_time))

    rows = ""
    entities_boosts = getMergedEntities()

    for i, entity_boost in enumerate(entities_boosts):
        entity = entity_boost[0]
        boost = entity_boost[1]
        entityScore = entity.getAvgLabelScore()
        scorePercentage = round((entityScore+1.0)/2.0*100)
        label = "Positive" if entityScore > 0.15 else ("Negative" if entityScore < -0.15 else "Neutral")
        label2 = "success" if label == "Positive" else ("danger" if label == "Negative" else "warning")



        r,g,b = 0,0,0

        if scorePercentage <= 50:
            g = round(255.0 * (scorePercentage / 50.0))
            r = 255
        else:
            g = 255
            r = round(255 * ((50.0 - (scorePercentage-1) % 50.0) / 50.0))

        rgb = "rgb(" + str(r) + "," + str(g) + "," + str(b) + ")"

        color = ""
        label = ""

        if scorePercentage > 80:
            label = "Positive"
            color = "#64CF39;"
        elif scorePercentage > 60:
            label = "Slightly Positive"
            color = "#9ED03A;"
        elif scorePercentage > 40:
            label = "Neutral"
            color = "#FFFF00; color: #333333;"
        elif scorePercentage > 20:
            label = "Slightly Negative"
            color = "#FF8000;"
        else:
            label = "Negative"
            color = "#FF0000;"

        #todo:
        desc = entity.dbpedia_data[2]

        leftLabel = '<strong style="color: rgba(240,0,0,1); position: relative; top: 1px; left:-4px;  font-size: 9px;">N</strong>'
        rightLabel = '<strong style="color: rgba(0,200,0,1); position: relative; top: 1px; left:4px;  font-size: 9px;">P</strong>'

        rowStr = '<tr>\
                                    <th scope="row">' + str(i + 1) + '</th>\
                                    <td>' + '<span data-toggle="tooltip" data-placement="right" title="'+desc+'">'+entity.name+'</span>' + frontend.popoverWithLinks(entity.links,i) +'</td>\
                                    <td>' + str(entity.getFrequency()+boost) + '</td>\
                                    <td>\
                                        <div><span class="badge" style="background-color: '+color+'">'+label+'</span><br><br>\
                                        '+leftLabel+'<input type="range" min="0" max="100" value="'+str(scorePercentage)+'" step="1" class="range" disabled/>'+rightLabel+'\
                                        </div>\
                                    </td>\
                                </tr>'


        rows += rowStr

    htmlString = htmlString.replace("$ROWS", rows)
    html_index = htmlString

def updateFrontend2():
    global html_survey
    p_processed = 0
    p_urls = userData.urls.values()
    for p_url in p_urls:
        if (p_url.processed):
            p_processed += 1

    htmlString = template_survey

    rows = ""
    entities_boosts = getMergedEntities()

    for i, entity_boost in enumerate(entities_boosts):
        entity = entity_boost[0]
        boost = entity_boost[1]
        entityScore = entity.getAvgLabelScore()
        scorePercentage = round((entityScore+1.0)/2.0*100)
        label = "Positive" if entityScore > 0.15 else ("Negative" if entityScore < -0.15 else "Neutral")
        label2 = "success" if label == "Positive" else ("danger" if label == "Negative" else "warning")



        r,g,b = 0,0,0

        if scorePercentage <= 50:
            g = round(255.0 * (scorePercentage / 50.0))
            r = 255
        else:
            g = 255
            r = round(255 * ((50.0 - (scorePercentage-1) % 50.0) / 50.0))

        rgb = "rgb(" + str(r) + "," + str(g) + "," + str(b) + ")"

        color = ""
        label = ""

        if scorePercentage > 80:
            label = "Positive"
            color = "#64CF39;"
        elif scorePercentage > 60:
            label = "Slightly Positive"
            color = "#9ED03A;"
        elif scorePercentage > 40:
            label = "Neutral"
            color = "#FFFF00; color: #333333;"
        elif scorePercentage > 20:
            label = "Slightly Negative"
            color = "#FF8000;"
        else:
            label = "Negative"
            color = "#FF0000;"


        sent_counts = [0,0,0] #neg, neu, pos
        for sent_label in entity.labels:
            sent_counts[int(sent_label)+1] += 1

        leftLabel = '<strong style="color: rgba(240,0,0,1); position: relative; top: -6px; left:-4px;  font-size: 9px;">N</strong>'
        rightLabel = '<strong style="color: rgba(0,200,0,1); position: relative; top: -6px; left:4px;  font-size: 9px;">P</strong>'
        rowStr ='<tr class="entityRow">' \
                '<th scope="row">' + str(i + 1) + '</th>'\
                '<td>' + entity.name + '</td>' \
                '<td class="sent_counts" style="display: none;">' + str(sent_counts) + '</td>'\
                '<td>'+' <div> <span class ="badge" style="background-color: ' + color + '"> ' + label + ' </span> <br> <br> '+leftLabel+'<input type="range" min="0" max="100" value="' + str(scorePercentage) + '" step="1" list="steplist" class ="range round" onload="updateTextInput(this);" oninput="updateTextInput(this);" style="pointer-events: none;" disabled/> '+rightLabel+' <datalist id="steplist"><option>10</option><option>30</option><option>50</option><option>70</option><option>90</option></datalist> </div> </td>' \
                '<td><div class="radio"><label><input class = "inputRad" type="radio" value = "A" name="rad'+str(i)+'" onchange="radioEvent(this);"> Agree</label></div>' \
                '<div class="radio"><label><input class = "inputRad" type="radio" value = "B" name="rad'+str(i)+'" onchange="radioEvent(this);"> Disagree (Please correct it)</label></div>' \
                '<div class="radio"><label><input class = "inputRad" type="radio" value = "C" name="rad'+str(i)+'" onchange="radioEvent(this);"> Don\'t care about entity</label></div></td>' \
                '<td>' + ' <div class="customCorrection" style = "opacity: 0.3; pointer-events: none;"> <span class ="badge" style="background-color: ' + color + '"> ' + label + ' </span> <br> <br> '+leftLabel+'<input type="range" min="0" max="100" value="' + str(scorePercentage) + '"data-customStartValue="' + str(scorePercentage) + '" step="1" list="steplist" class ="range round" onload="updateTextInput(this);" oninput="updateTextInput(this);"/>'+rightLabel+' <datalist id="steplist"><option>10</option><option>30</option><option>50</option><option>70</option><option>90</option></datalist> </div> </td>' \
                '</tr>'
        rows += rowStr

    htmlString = htmlString.replace("$ROWS", rows)
    html_survey = htmlString

def runServer():

    log("running at port "+str(server.socket.getsockname()[1]))
    server.serve_forever()

def save():
    log("Save")
    with survey_lock:
        userData.survey_week = user_survey_week
    userDataFile = open(USER_DATA, mode='wb')
    pickle.dump(userData, userDataFile)
    userDataFile.close()

def copyChromeFile():
    log("Copying chrome history file.")
    path = None

    if os.name == 'nt':
        path = os.path.expanduser('~') + r"\AppData\Local\Google\Chrome\User Data\Default"
    else:
        path = os.path.expanduser('~') + "/Library/Application Support/Google/Chrome/Default"

    finalPath = os.path.join(path, 'history')

    copyfile(finalPath, HOME_PATH + "/history.db")

    log("Successfully copied chrome history file.")

def isBlacklisted(host):
    if (host == None):
        return True
    parts = host.split(".")
    finalDomain = ""
    if len(parts) <= 1:
        return True
    isDouble = False
    for doubleSuffix in blacklists.SUFFIX_WHITELIST_TWO:
        if host.endswith(doubleSuffix):
            isDouble = True
            break
    if isDouble:
        finalDomain = ".".join(parts[:-2])
    else:
        finalDomain = ".".join(parts[:-1])

    for domain in blacklists.DOMAIN_BLACKLIST:
        if ('.'+finalDomain).endswith('.'+domain):
            return True
    return False

def isGraylisted(host):
    if (host == None):
        return False
    parts = host.split(".")
    finalDomain = ""
    if len(parts) <= 1:
        return False
    isDouble = False
    for doubleSuffix in blacklists.SUFFIX_WHITELIST_TWO:
        if host.endswith(doubleSuffix):
            isDouble = True
            break
    if isDouble:
        finalDomain = ".".join(parts[:-2])
    else:
        finalDomain = ".".join(parts[:-1])

    for domain in gray_list:
        if ('.'+finalDomain).endswith('.'+domain):
            return True
    return False

def survey_due():
    with survey_lock:
        last_week_num = user_survey_week
    current_week_num = get_survey_week()
    return last_week_num < current_week_num

def check_survey_reminder():
    global last_reminder_time


    # Send a reminder.
    if survey_due() and (last_reminder_time is None or (datetime.datetime.now()-last_reminder_time).total_seconds() > 3600*6):
        last_reminder_time = datetime.datetime.now()

        log("Launch browser survey popup")
        #answer = messagebox.askyesno("Survey Reminder","You have a survey due.")
        # Run this in background thread to prevent blocking the interface (b/c for some reason on windows it blocks)
        tr = threading.Thread(target=openBrowser, args=[port])
        tr.daemon = True  # This forces the child thread to exit whenever the parent (main) exits.
        tr.start()






def refresh():
    global old_time, last_process_time, is_sleeping, count, persons_dict, reset_user_data, user_survey_week
    if old_time != None and time.time() - old_time < 60*60*project_constants.SLEEP_TIME:  # Every 12 hours.
        #print("Skip because sleeping.")
        return

    with refresh_lock:
        log("Refresh")
        is_sleeping = False
        last_process_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        global userData

        copyChromeFile()

        userDataFile = None

        userData = UserData()
        error = False
        if reset_user_data is False and os.path.exists(USER_DATA):
            try:
                userDataFile = open(USER_DATA, 'rb')
                userData = pickle.load(userDataFile)

            except Exception as e:
                log("ERROR - FAILED TO LOAD USER DATA FILE: "+str(e))
                error = True

            if userDataFile != None:
                userDataFile.close()

            if error:
                os._exit(1)
        reset_user_data = False
        with survey_lock:
            user_survey_week = userData.survey_week
        db = sqlite3.connect(HISTORY_COPY, timeout=30)
        cursor = db.cursor()
        # Fetches top 6000 most recent URLs that are not hidden, have a view count. Further processing checks if the URLs are within the past year, and not blacklisted etc.
        # DO NOT DO (AND urls.title != "") because sometimes Chrome does not give a title when it should and sometimes article titles will get removed or added at a later time. Strange behavior.
        query = 'SELECT urls.url, urls.last_visit_time FROM urls WHERE urls.hidden = 0 AND urls.visit_count > 0 ORDER BY urls.last_visit_time DESC LIMIT 0,6000'
        cursor.execute(query)
        rows = [row for row in cursor.fetchall()]

        db.close()
        log("Extracted links from chrome db.")
        for row in rows:
            link = row[0]
            link_time = row[1]
            t1 = datetime.datetime(1601, 1, 1) + datetime.timedelta(microseconds=link_time)
            t2 = datetime.datetime.now()
            if (t2 - t1).total_seconds() > project_constants.RECORD_TIME_LIMIT:
                log("Stop fetching links because > year.")
                break # Rows are in DESC order (oldest last) so no need to keep recording.
            linkData = parse.urlsplit(link)
            if linkData == None or linkData.hostname == None or linkData.path == None:
                log("Skip, invalid link: "+str(link))
                continue
            # Small but effective.
            link_path = linkData.path
            if link_path.endswith(".png") or link_path.endswith(".jpg") or link_path.endswith(".gif") or link_path.endswith(".gifv"):
                log("Skip, invalid link: " + str(link))
                continue

            hostname = linkData.hostname.lower()
            hostnameTrim = hostname[len("www."):] if hostname.startswith("www.") else hostname
            if isBlacklisted(hostnameTrim):
                #print("BLACKLISTED "+linkData.hostname.lower())
                continue

            if link.lower() in userData.urls:
                continue

            isGray = isGraylisted(hostnameTrim)
            userData.urls[link.lower()] = UserDataURL(link, False, isGray, link_time)

        count = 0
        log("Links pre-processed.")
        sorted_urls = sorted(userData.urls.items(), key=lambda x: x[1].timeVisited, reverse=True)



    # Time to process
    for key,url in sorted_urls:
        with refresh_lock:
            if url.processed:
                #print("skip")
                continue

            if count%4 == 0:
                    save()
            if count >= project_constants.CAP:
                break


        time.sleep(random.randint(15, 30))


        try:
            #print("processing")
            article = Article(url.url)
            article.download()
            article.parse()
            document = article.title+"\n"+article.text

            with refresh_lock:
                url.processed = True
                count += 1

                # Article validation. Make sure it was extracted properly, it is english, and it's not a duplicate.
                if len(document) < 100:
                    log("*** Article validation failed so ignoring. Reason: Too short. Link: " + url.url)
                    continue
                if len(document) > 100000:
                    log("*** Article validation failed so ignoring. Reason: Too long. Link: " + url.url)
                    continue

                sample_content = article.text[:2500]
                articleHash = sha256(sample_content.encode('utf8', errors="ignore")).hexdigest()
                hash_test = False
                # Note it will test against itself but it will be None at this point so it doesn't matter.
                for key_2, url_2 in sorted(userData.urls.items(), key=lambda x: x[1].timeVisited, reverse=True):
                    if url_2.hash != None and url_2.hash == articleHash:
                        hash_test = True
                        break

                if hash_test:
                    log("*** Article validation failed so ignoring. Reason: Duplicate hash. Link: " + url.url)
                    continue

                url.hash = articleHash # At this point it is safe to assign the hash. Duplicates and other articles with issues will have None for hash.

            if detect(sample_content) != 'en':
                log("*** Article validation failed so ignoring. Reason: Not in english. Link: " + url.url)
                continue




            entitySentiments = entitySentimentAnalyzer.analyze(document)[:5] #todo: We pick top 5 from article. Better to use title for advantage.!

            for entitySentiment in entitySentiments:
                nameKey = entitySentiment.name.lower()
                bucketScore = float(-1.0 if entitySentiment.score < NEUTRAL_THRESHOLD_LOWER else (1.0 if entitySentiment.score > NEUTRAL_THRESHOLD_UPPER else 0.0))
                d = None
                if nameKey in persons_dict:
                    d = persons_dict[nameKey]
                else:
                    # print('UNKNOWN ENTITY: ' + nameKey)
                    parts = nameKey.split(' ')
                    if len(parts) >= 2:
                        nameKeyTmp = parts[0] + ' ' + parts[-1]
                        firstKeyTmp = parts[0]
                        lastKeyTmp = parts[-1]
                        if nameKeyTmp in persons_dict:
                            nameKey = nameKeyTmp
                            d = persons_dict[nameKey]
                        elif firstKeyTmp in persons_dict and (getLast(persons_dict[firstKeyTmp][0]).lower() == lastKeyTmp or getLast(persons_dict[firstKeyTmp][0]) == ''):
                            nameKey = firstKeyTmp
                            d = persons_dict[firstKeyTmp]
                        elif lastKeyTmp in persons_dict and (persons_dict[lastKeyTmp][0].lower().split(' ')[0] == firstKeyTmp):
                            nameKey = lastKeyTmp
                            d = persons_dict[lastKeyTmp]
                        #else:
                            #print('Ignoring UNKNOWN ENTITY: ' + nameKey)

                    #elif len(parts) == 1:
                        # Singular names not in the db, will be linked to dbpedia entities.
                        #print('Ignoring UNKNOWN ENTITY: ' + nameKey)
                    #else:
                        #print('Ignoring UNKNOWN ENTITY: ' + nameKey)

                # Assertion
                if nameKey not in persons_dict or d is None:
                    db_data = None
                else:
                    if d[0].startswith('_'):  # alias
                        nameKey = d[0][1:]
                        d = persons_dict[nameKey]
                        #print('Found ALIAS to ' + nameKey)

                    db_data = [nameKey, d[0], d[1]]

                with refresh_lock:
                    if nameKey in userData.entities:
                        userEntity = userData.entities[nameKey]
                        userEntity.labels.append(bucketScore)
                        userEntity.links.append(url.url)
                    else:
                        userData.entities[nameKey] = UserDataEntity(entitySentiment.name)
                        userData.entities[nameKey].labels.append(bucketScore)
                        userData.entities[nameKey].links.append(url.url)
                        userData.entities[nameKey].dbpedia_data = db_data


        except Exception as e:
            log('Skip article processing due to Error: ' + str(e))
            continue


    with refresh_lock:
        is_sleeping = True
        save()
    log("Done refreshing. Sleeping for "+str(project_constants.SLEEP_TIME)+" hours")

    old_time = time.time()

def runSystem():

    log('Core loop')
    while True:
        try:
            refresh()
            check_survey_reminder()
            time.sleep(random.randint(60, 120))
        except Exception as exp:
            log("************************************* EXCEPTION IN CORE THREAD *************************************")
            log("EXCEPTION = " + str(exp))
            log(traceback.format_exc())
            time.sleep(60) #Just in case we get stuck in an error loop



def openBrowser(port):
    chrome_path = 'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe %s' if os.name == 'nt' else 'open -a /Applications/Google\ Chrome.app %s'
    if not isinstance(port, int):
        raise ValueError('Invalid port')
    log("Open Browser with available: "+str(webbrowser._browsers))
    url = "http://localhost:"+str(port)
    try:
        if not webbrowser.get(chrome_path).open(url):
            log("Error opening chrome browser. Trying generic.")
            webbrowser.open(url)
    except:
        log("Error opening browser. Trying again with generic.")
        webbrowser.open(url)

def button_action():
    #Run this in background thread to prevent blocking the interface (b/c for some reason on windows it blocks)
    log("Launch browser")
    tr = threading.Thread(target=openBrowser, args=[port])
    tr.daemon = True  # This forces the child thread to exit whenever the parent (main) exits.
    tr.start()

def disable_event():
    global window
    window.wm_state('iconic')

def quit_action():
    answer = messagebox.askyesno("WARNING", "WARNING: ARE YOU SURE YOU WANT TO QUIT?\n\nThe user study will stop. You can resume"
                                            " the study by running the application again. If you are looking to completely uninstall, "
                                            "select the 'uninstall' button in the dashboard.")
    if answer:
        with refresh_lock:
            log('USER CHOSE TO QUIT THE APPLICATION')
            os._exit(0)

def initGUI():
    global window
    log("Init GUI")
    window = Tk()
    window.config(menu=Menu(window))



    window.title("Privacy Project User Study")
    window.protocol("WM_DELETE_WINDOW", disable_event)
    m = Message(window,
                text="Welcome to the user study. This application must remain open for the system to work. You may "
                     "minimize it but do not quit it or the system will stop. If you quit it, simply launch "
                     "the application again and the system will resume. \nYou can press the \"Open Dashboard\" button at any time to "
                     "start a survey or view more information about the system. Please complete a survey each week for one month.", width=495, justify=CENTER)
    window.geometry('600x200')
    window.resizable(False, False)


    m.grid(column=1, row=1)

    btn = Button(window, text="Open Dashboard", command=button_action)

    btn.grid(column=1, row=2)

    quit_btn = Button(window, text="Quit", command=quit_action)

    quit_btn.grid(column=0, row=0)



    #Mac Mojave Text Render bug fix
    window.update()
    window.geometry('600x201')

    #Fix mac re-open minimized window bug
    if sys.platform == "darwin":
        window.createcommand('tk::mac::ReopenApplication', window.deiconify)
    log("GUI Done")
    window.mainloop()

def writeAutostartupFiles():
    if os.name == 'nt':
        autostart__path_folder = str(Path.home())+'\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup'
        path_to_exe = get_app_path()+'\privacy-project.exe'

        from win32com.client import Dispatch

        shell = Dispatch('WScript.Shell')
        shortcut = shell.CreateShortCut(autostart__path_folder+'\privacy-project.lnk')
        shortcut.Targetpath = path_to_exe
        shortcut.WorkingDirectory = autostart__path_folder
        shortcut.IconLocation = path_to_exe
        shortcut.save()

    else:
        with open(MAC_USER_AGENT_PATH + '/' + MAC_USER_AGENT_ID + '.plist', "w") as ver_file:
            ver_file.write(MAC_AGENT_XML)

        with open(HOME_PATH + "/autorun.sh", "w") as ver_file:
            ver_file.write(MAC_AUTORUN_SCRIPT)

        os.chmod(HOME_PATH + "/autorun.sh", 0o744)

# TODO: Remember to handle version if ever installing a new version with the previous installed to prevent using old data file.
def writeVersionFile():
    global start_date, reset_user_data
    #datetime.datetime.now()

    #First try to read and parse existing file. If it fails, it means there was no parsable file.
    try:
        with open(HOME_PATH + "/version", "rb") as ver_file:
            content = json.load(ver_file)
            if not isinstance(content,dict):
                raise ValueError("Failed to parse json.")
            if not "version" in content:
                raise ValueError("Failed to parse json.")
            ver = content["version"]
            if not isinstance(ver,int):
                raise ValueError("Failed to parse json.")

            #TODO: The user is installing with an old version already installed. Handle appropriately for the new ver.
            #TODO: It probably makes sense to just not load the data file and create a new version file.
            if ver != project_constants.VERSION_NUM:
                log("**** WARNING: Old version previously installed. ****")
                # Throw error which will create a new version file. Old data will remain.
                raise ValueError("Old version file.")
            else: # Read data.

                start_date = content["start_date"]

    except:
        log("Failed to open and parse json. So creating a new install.")
        start_date = datetime.datetime.now().strftime("%Y-%m-%d")
        reset_user_data = True #todo: Important, currently always wiping data when version files fails (new install)
        content = {"version":project_constants.VERSION_NUM,"start_date":start_date}
        with open(HOME_PATH + "/version", "w") as ver_file:
            json.dump(content, ver_file, indent=1)



if __name__ == '__main__':
    log("- - - - MAIN START - - - -")
    try:

        port = None

        try:
            me = SingleInstance()
        except SingleInstanceException as e:
            log('NOT RUNNING BECAUSE ALREADY RUNNING!')
            exit(1)

        with open(get_app_path()+"/res/index_template.html", 'r') as index_template_file:
            template_index = index_template_file.read()
        with open(get_app_path()+"/res/survey_template.html", 'r') as survey_template_file:
            template_survey = survey_template_file.read()
        with open(get_app_path()+"/res/thanks.html", 'r') as thanks_file:
            template_thanks = thanks_file.read()

        log("static html templates loaded")

        server = socketserver.TCPServer(('localhost', 0), MyRequestHandler)
        port = server.socket.getsockname()[1]
        log("Socket created.")
        writeVersionFile()
        log("Version file created.")

        # try for auto-startup but if it fails it is not essential.
        # In testing we found it fails if the user's system is not setup as usual,
        # for example, the launch agents folder missing on mac or incorrect home paths on
        # windows with cygwin installed.
        log("Creating Auto-startup files.")
        try:
            writeAutostartupFiles()
        except Exception as e2:
            log('Error creating the auto-startup files. Error: '+str(e2))

        with open(get_app_path()+'/res/gray_list.csv','r',encoding='UTF-8') as gray_list_file: #utf-8 required!
            gray_list = [x[0] for x in list(csv.reader(gray_list_file)) if len(x) > 0]

        with open(get_app_path()+'/res/dbpedia_persons.json', encoding='utf-8') as file:
            persons_dict = json.load(file)

        import nltk
        nltk.data.path.append(get_app_path()+'/res/nltk_data')
        entitySentimentAnalyzer = EntitySentimentAnalyzer()

        thread2 = threading.Thread(target=runSystem)
        thread2.daemon = True
        thread2.start()

        thread = threading.Thread(target=runServer)
        thread.daemon = True  # This forces the child thread to exit whenever the parent (main) exits.
        thread.start()


        initGUI()
    except Exception as exp:
        log("************************************* EXCEPTION IN CORE THREAD *************************************")
        log("EXCEPTION = " + str(exp))
        log(traceback.format_exc())
        os._exit(1)
    log("- - - - QUIT - - - -")
