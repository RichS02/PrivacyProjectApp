import logging
from pathlib import Path
import os, errno
HOME_PATH = str(Path.home())+"/com.stony-brook.nlp.privacy-project"
try:
    os.makedirs(HOME_PATH)
except OSError as e:
    if e.errno != errno.EEXIST:
        raise ValueError('Failed to create home directory. Error code: '+str(e.errno))

logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p', filename=HOME_PATH+'/system.log',level=logging.WARNING)

def log(mes):
    print(str(mes))
    logging.warning(str(mes))

log("- - - - SYSTEM STARTING - - - -")

# Set the current working directory for python http server socket for front end.
os.chdir(HOME_PATH)

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
import sys
import traceback
import datetime
import frontend
import csv
from langdetect import detect
from hashlib import sha256

log("Imports finished.")

CHROME_HISTORY_SQLITE_FILE = "history"
HISTORY_COPY = HOME_PATH+"/history.db"
USER_DATA = HOME_PATH+"/user-data.bin"
INDEX = HOME_PATH+"/index.html"
SURVEY = HOME_PATH+"/survey.html"
ROW_URL = 0
CAP = 100
NEUTRAL_THRESHOLD_UPPER = 0.114
NEUTRAL_THRESHOLD_LOWER = -0.062
RECORD_TIME_LIMIT = 31540000  # Seconds
userData = None
old_time = None
last_process_time = None
is_sleeping = False
count = 0
gray_list = []

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

MAC_AUTORUN_SCRIPT = '#!/bin/sh\nopen -a "privacy-project-0.8.app"'

class UserDataEntity:
    def __init__(self, name):
        self.name = name
        self.labels = [] #-1 neg , 0 neu, 1 pos
        self.links = [] #Aligns with labels.

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

class MyRequestHandler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        log("Get request: "+str(self.path))
        if self.path == '/':
            self.path = '/index.html'
        return http.server.SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        log("Post request: " + str(self.path))
        len = int(self.headers.get('Content-Length'))
        body = self.rfile.read(len).decode('utf8',errors="ignore")
        if 'uninstall' in body:
            uninstall()
        if self.path == '/':
            self.path = '/index.html'
        return http.server.SimpleHTTPRequestHandler.do_GET(self)

# Handle uninstalling safely.
def uninstall():
    try:
        os.remove(HOME_PATH+"/version")
        if os.name != 'nt':
            os.remove(HOME_PATH + "/autorun.sh")
        os.remove(HOME_PATH + "/system.log")
        os.remove(HOME_PATH + "/user-data.bin")
        os.remove(HOME_PATH + "/index.html")
        os.remove(HOME_PATH + "/survey.html")
        os.remove(HOME_PATH + "/history.db")
        os.rmdir(HOME_PATH)
        if os.name != 'nt':
            os.remove(MAC_USER_AGENT_PATH + '/' + MAC_USER_AGENT_ID + '.plist')
    except e:
        pass

    os._exit(1)


def getMergedEntities():
    uEntities = copy.deepcopy(list(userData.entities.values()))
    uEntitiesCopy = copy.deepcopy(uEntities) #Very important to use copy to prevent double counting merges. todo Though this could be fixed by limiting merges.
    entitiesToRemove = []
    final = [] # [entity,boost] (2x weight to entity frequency if in gray list so it has greater chance of appearing in top 30)
    for i in range(0,len(uEntitiesCopy)):
        match = False
        for j in range(0, len(uEntitiesCopy)):
            if uEntitiesCopy[i].name == uEntitiesCopy[j]:
                continue

            splitNamei = uEntitiesCopy[i].name.split()
            splitNamej = uEntitiesCopy[j].name.split()

            # todo: maybe Merge based on highest. Merge Obama to only one entity with the highest frequency. So Obama -> Barack Obama not Window Obama.
            if len(splitNamei) == 1 and len(splitNamej) > 1 and splitNamei[0].strip().lower() == splitNamej[-1].strip().lower() and uEntitiesCopy[j].getFrequency() >= uEntitiesCopy[i].getFrequency():
                #uEntities[j].score = (uEntities[j].score*float(uEntities[j].frequency) + uEntitiesCopy[i].score*float(uEntitiesCopy[i].frequency))/float(uEntities[j].frequency + uEntitiesCopy[i].frequency)
                uEntities[j].labels += uEntities[i].labels
                uEntities[j].links += uEntities[i].links
                print("MERGED: "+uEntitiesCopy[i].name+" to "+uEntities[j].name)
                match = True

            '''if len(splitNamei) == 1 and len(splitNamej) > 1 and splitNamei[0].strip().lower() == splitNamej[0].strip().lower() and uEntitiesCopy[j].frequency >= uEntitiesCopy[i].frequency:
                uEntities[j].score = (uEntities[j].score*float(uEntities[j].frequency) + uEntitiesCopy[i].score*float(uEntitiesCopy[i].frequency))/float(uEntities[j].frequency + uEntitiesCopy[i].frequency)
                uEntities[j].frequency += uEntitiesCopy[i].frequency
                uEntities[j].links = uEntities[j].links.union(uEntities[i].links)
                #print("MERGED: "+uEntitiesCopy[i].name+" to "+uEntities[j].name)
                match = True

            if len(splitNamei) == 2 and len(splitNamej) > 2 and splitNamei[0].strip().lower() == splitNamej[0].strip().lower() and splitNamei[1].strip().lower() == splitNamej[-1].strip().lower():
                uEntities[j].score = (uEntities[j].score*float(uEntities[j].frequency) + uEntitiesCopy[i].score*float(uEntitiesCopy[i].frequency))/float(uEntities[j].frequency + uEntitiesCopy[i].frequency)
                uEntities[j].frequency += uEntitiesCopy[i].frequency
                print("MERGED: "+uEntitiesCopy[i].name+" to "+uEntities[j].name)
                uEntities[j].links = uEntities[j].links.union(uEntities[i].links)
                match = True'''

        if match:
            entitiesToRemove.append(uEntitiesCopy[i].name)


    for e in uEntities:
        if e.name not in entitiesToRemove:
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




def updateFrontend():
    log("Update frontend.")
    global count
    p_processed = 0
    p_urls = userData.urls.values()
    for p_url in p_urls:
        if (p_url.processed):
            p_processed += 1



    htmlTemplateFile = open(get_app_path()+"/res/index_template.html", 'r')
    htmlString = htmlTemplateFile.read()
    htmlTemplateFile.close()

    htmlString = htmlString.replace("$STATUS", "Sleeping" if is_sleeping else "Processing")
    htmlString = htmlString.replace("$CURRENT_ARTICLES", str(count)+"/"+str(CAP))
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

        leftLabel = '<strong style="color: rgba(240,0,0,1); position: relative; top: 1px; left:-4px;  font-size: 9px;">N</strong>'
        rightLabel = '<strong style="color: rgba(0,200,0,1); position: relative; top: 1px; left:4px;  font-size: 9px;">P</strong>'

        rowStr = '<tr>\
                                    <th scope="row">' + str(i + 1) + '</th>\
                                    <td>' + entity.name + frontend.popoverWithLinks(entity.links,i) +'</td>\
                                    <td>' + str(entity.getFrequency()+boost) + '</td>\
                                    <td>\
                                        <div><span class="badge" style="background-color: '+color+'">'+label+'</span><br><br>\
                                        '+leftLabel+'<input type="range" min="0" max="100" value="'+str(scorePercentage)+'" step="1" class="range" disabled/>'+rightLabel+'\
                                        </div>\
                                    </td>\
                                </tr>'


        rows += rowStr

    htmlString = htmlString.replace("$ROWS", rows)
    indexFile = open(INDEX, "wb")
    indexFile.write(htmlString.encode('utf8',errors="ignore"))
    indexFile.close()
    updateFrontend2()



def updateFrontend2():
    p_processed = 0
    p_urls = userData.urls.values()
    for p_url in p_urls:
        if (p_url.processed):
            p_processed += 1



    htmlTemplateFile = open(get_app_path()+"/res/survey_template.html", 'r')
    htmlString = htmlTemplateFile.read()
    htmlTemplateFile.close()

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


        leftLabel = '<strong style="color: rgba(240,0,0,1); position: relative; top: -6px; left:-4px;  font-size: 9px;">N</strong>'
        rightLabel = '<strong style="color: rgba(0,200,0,1); position: relative; top: -6px; left:4px;  font-size: 9px;">P</strong>'
        rowStr ='<tr class="entityRow">' \
                '<th scope="row">' + str(i + 1) + '</th>'\
                '<td>' + entity.name + '</td>' \
                '<td>'+' <div> <span class ="badge" style="background-color: ' + color + '"> ' + label + ' </span> <br> <br> '+leftLabel+'<input type="range" min="0" max="100" value="' + str(scorePercentage) + '" step="1" list="steplist" class ="range round" onload="updateTextInput(this);" oninput="updateTextInput(this);" style="pointer-events: none;" disabled/> '+rightLabel+' <datalist id="steplist"><option>10</option><option>30</option><option>50</option><option>70</option><option>90</option></datalist> </div> </td>' \
                '<td><div class="radio"><label><input class = "inputRad" type="radio" value = "A" name="rad'+str(i)+'" onchange="radioEvent(this);"> Agree</label></div>' \
                '<div class="radio"><label><input class = "inputRad" type="radio" value = "B" name="rad'+str(i)+'" onchange="radioEvent(this);"> Disagree (Please correct it)</label></div>' \
                '<div class="radio"><label><input class = "inputRad" type="radio" value = "C" name="rad'+str(i)+'" onchange="radioEvent(this);"> Don\'t care about entity</label></div></td>' \
                '<td>' + ' <div class="customCorrection" style = "opacity: 0.3; pointer-events: none;"> <span class ="badge" style="background-color: ' + color + '"> ' + label + ' </span> <br> <br> '+leftLabel+'<input type="range" min="0" max="100" value="' + str(scorePercentage) + '"data-customStartValue="' + str(scorePercentage) + '" step="1" list="steplist" class ="range round" onload="updateTextInput(this);" oninput="updateTextInput(this);"/>'+rightLabel+' <datalist id="steplist"><option>10</option><option>30</option><option>50</option><option>70</option><option>90</option></datalist> </div> </td>' \
                '</tr>'
        rows += rowStr

    htmlString = htmlString.replace("$ROWS", rows)
    indexFile = open(SURVEY, "wb")
    indexFile.write(htmlString.encode('utf8',errors="ignore"))
    indexFile.close()

def runServer():
    print("******************************************B " + str(threading.get_ident()))
    log("running at port "+str(server.socket.getsockname()[1]))
    server.serve_forever()

def save():
    log("Save")
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


def refresh():
    global old_time, last_process_time, is_sleeping, count
    if old_time != None and time.time() - old_time < 60*60*12:  # Every 12 hours.
        print("Skip because sleeping.")
        return

    print("******************************************refresh" + str(threading.get_ident()))
    log("Refresh")
    is_sleeping = False
    last_process_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    global userData

    copyChromeFile()

    userDataFile = None

    userData = UserData()
    error = False
    if os.path.exists(USER_DATA):
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
        if (t2 - t1).total_seconds() > RECORD_TIME_LIMIT:
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
    updateFrontend()



    # Time to process
    for key,url in sorted(userData.urls.items(), key=lambda x: x[1].timeVisited, reverse=True):
        if url.processed:
            #print("skip")
            continue

        if count%4 == 0:
            updateFrontend()
            save()
        if count >= 100:
            break


        time.sleep(random.randint(15, 30))


        try:
            #print("processing")
            article = Article(url.url)
            article.download()
            article.parse()
            document = article.title+"\n"+article.text

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

                if nameKey in userData.entities:
                    userEntity = userData.entities[nameKey]
                    userEntity.labels.append(bucketScore)
                    userEntity.links.append(url.url)
                else:
                    userData.entities[nameKey] = UserDataEntity(entitySentiment.name)
                    userData.entities[nameKey].labels.append(bucketScore)
                    userData.entities[nameKey].links.append(url.url)


        except Exception as e:
            log('Skip article processing due to Error: ' + str(e))
            continue

    is_sleeping = True
    updateFrontend()
    save()
    log("Done refreshing. Sleeping for 12 hours")

    old_time = time.time()

def runSystem():
    print("******************************************run system " + str(threading.get_ident()))
    log('Core loop')
    while True:
        try:
            refresh()
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


def initGUI():
    global window
    log("Init GUI")
    window = Tk()




    window.title("Privacy Project User Study")
    window.protocol("WM_DELETE_WINDOW", disable_event)
    m = Message(window,
                text="Welcome to the user study. This application must remain open for the system to work. You may "
                     "minimize it but do not close it or the system will stop. If you close it, simply launch "
                     "the application again and the system will resume. \nYou can press the \"Open Dashboard\" button at any time to "
                     "start a survey or view more information about the system. Please complete a survey once a week for the duration of the study.", width=495, justify=CENTER)
    window.geometry('500x200')
    window.resizable(False, False)
    m.pack()

    m.grid(column=0, row=0)

    btn = Button(window, text="Open Dashboard", command=button_action)

    btn.grid(column=0, row=1)

    log("GUI Done")

    window.mainloop()

def writeAutostartupFiles():
    if os.name == 'nt':
        print("TODO") #TODO
    else:
        with open(MAC_USER_AGENT_PATH + '/' + MAC_USER_AGENT_ID + '.plist', "w") as ver_file:
            ver_file.write(MAC_AGENT_XML)

        with open(HOME_PATH + "/autorun.sh", "w") as ver_file:
            ver_file.write(MAC_AUTORUN_SCRIPT)

        os.chmod(HOME_PATH + "/autorun.sh", 0o744)



if __name__ == '__main__':
    log("- - - - MAIN START - - - -")

    port = None

    try:
        me = SingleInstance()
    except SingleInstanceException as e:
        log('NOT RUNNING BECAUSE ALREADY RUNNING!')
        exit(1)



    server = socketserver.TCPServer(('localhost', 0), MyRequestHandler)
    port = server.socket.getsockname()[1]
    log("Socket created.")
    with open(HOME_PATH+"/version", "w") as ver_file:
        ver_file.write(str("1"))

    writeAutostartupFiles()
    log("Auto-startup files created.")
    with open(get_app_path()+'/res/gray_list.csv','r') as gray_list_file:
        gray_list = [x[0] for x in list(list(csv.reader(gray_list_file))) if len(x) > 0]


    import nltk
    nltk.data.path.append(get_app_path()+'/res/nltk_data')
    entitySentimentAnalyzer = EntitySentimentAnalyzer()

    thread2 = threading.Thread(target=runSystem)
    print("******************************************S2 " + str(threading.get_ident()))
    thread2.daemon = True
    thread2.start()

    thread = threading.Thread(target=runServer)
    print("******************************************S1 " + str(threading.get_ident()))
    thread.daemon = True  # This forces the child thread to exit whenever the parent (main) exits.
    thread.start()

    initGUI()
    log("- - - - QUIT - - - -")
