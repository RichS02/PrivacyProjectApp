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

def log(strr):
    print(str(strr))
    logging.warning(str(strr))

log("- - - - SYSTEM STARTING - - - -")

os.chdir(HOME_PATH) #Set the current working directory for python http server socket for front end.

#This is used for pyinstaller. We need to return a special path to application.
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

CHROME_HISTORY_SQLITE_FILE = "history"
HISTORY_COPY = HOME_PATH+"/history.db"
USER_DATA = HOME_PATH+"/user-data.bin"
INDEX = HOME_PATH+"/index.html"
SURVEY = HOME_PATH+"/survey.html"
ROW_URL = 0
CAP = 100
NEUTRAL_THRESHOLD_UPPER = 0.114
NEUTRAL_THRESHOLD_LOWER = -0.062
userData = None
old_time = None
last_process_time = None
is_sleeping = False
count = 0

class UserDataEntity:
    def __init__(self, name, score, frequency):
        self.name = name
        self.score = score
        self.frequency = frequency


class UserDataURL:
    def __init__(self, url, processed):
        self.url = url
        self.processed = processed


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

def getMergedEntities():
    uEntities = copy.deepcopy(list(userData.entities.values()))
    uEntitiesCopy = copy.deepcopy(uEntities) #Very important to use copy to prevent double counting merges. todo Though this could be fixed by limiting merges.
    entitiesToRemove = []
    final = []
    for i in range(0,len(uEntitiesCopy)):
        match = False
        for j in range(0, len(uEntitiesCopy)):
            if uEntitiesCopy[i].name == uEntitiesCopy[j]:
                continue

            splitNamei = uEntitiesCopy[i].name.split()
            splitNamej = uEntitiesCopy[j].name.split()


            if len(splitNamei) == 1 and len(splitNamej) > 1 and splitNamei[0].strip().lower() == splitNamej[-1].strip().lower() and uEntitiesCopy[j].frequency >= uEntitiesCopy[i].frequency:
                uEntities[j].score = (uEntities[j].score*float(uEntities[j].frequency) + uEntitiesCopy[i].score*float(uEntitiesCopy[i].frequency))/float(uEntities[j].frequency + uEntitiesCopy[i].frequency)
                uEntities[j].frequency += uEntitiesCopy[i].frequency
                #print("MERGED: "+uEntitiesCopy[i].name+" to "+uEntities[j].name)
                match = True

            if len(splitNamei) == 1 and len(splitNamej) > 1 and splitNamei[0].strip().lower() == splitNamej[0].strip().lower() and uEntitiesCopy[j].frequency >= uEntitiesCopy[i].frequency:
                uEntities[j].score = (uEntities[j].score*float(uEntities[j].frequency) + uEntitiesCopy[i].score*float(uEntitiesCopy[i].frequency))/float(uEntities[j].frequency + uEntitiesCopy[i].frequency)
                uEntities[j].frequency += uEntitiesCopy[i].frequency
                #print("MERGED: "+uEntitiesCopy[i].name+" to "+uEntities[j].name)
                match = True

            #if len(splitNamei) == 2 and len(splitNamej) > 2 and splitNamei[0].strip().lower() == splitNamej[0].strip().lower() and splitNamei[1].strip().lower() == splitNamej[-1].strip().lower():
            #    uEntities[j].score = (uEntities[j].score*float(uEntities[j].frequency) + uEntitiesCopy[i].score*float(uEntitiesCopy[i].frequency))/float(uEntities[j].frequency + uEntitiesCopy[i].frequency)
            #    uEntities[j].frequency += uEntitiesCopy[i].frequency
            #    print("MERGED: "+uEntitiesCopy[i].name+" to "+uEntities[j].name)
            #    match = True

        if match:
            entitiesToRemove.append(uEntitiesCopy[i].name)


    for e in uEntities:
        if e.name not in entitiesToRemove:
            final.append(e)
        #else:
            #print("Ignoring "+e.name)

    return sorted(final, key=lambda x: x.frequency, reverse=True)[:30]




def updateFrontend():
    log("Update frontend.")
    global count
    p_processed = 0
    p_urls = userData.urls.values()
    for p_url in p_urls:
        if (p_url.processed):
            p_processed += 1


    #todo: error checks
    htmlTemplateFile = open(get_app_path()+"/res/index_template.html", 'r')
    htmlString = htmlTemplateFile.read()
    htmlTemplateFile.close()

    htmlString = htmlString.replace("$STATUS", "Sleeping" if is_sleeping else "Processing")
    htmlString = htmlString.replace("$CURRENT_ARTICLES", str(count)+"/"+str(CAP))
    htmlString = htmlString.replace("$TOTAL_ARTICLES", str(p_processed) + "/" + str(len(p_urls)))
    htmlString = htmlString.replace("$LAST_TIME", str(last_process_time))

    rows = ""
    entities = getMergedEntities() #sorted(list(userData.entities.values()), key=lambda x: x.frequency, reverse=True)

    for i, entity in enumerate(entities):
        scorePercentage = round((entity.score+1.0)/2.0*100)
        label = "Positive" if entity.score > 0.15 else ("Negative" if entity.score < -0.15 else "Neutral")
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

        rowStr = '<tr>\
                                    <th scope="row">' + str(i + 1) + '</th>\
                                    <td>' + entity.name + '</td>\
                                    <td>' + str(entity.frequency) + '</td>\
                                    <td style="text-align: center;">\
                                        <div><span class="badge" style="background-color: '+color+'">'+label+'</span><br><br>\
                                        <input type="range" min="0" max="100" value="'+str(scorePercentage)+'" step="1" class="range" disabled/>\
                                        </div>\
                                    </td>\
                                </tr>'

        #rowStr = "<tr>\
        #                    <th scope=\"row\">"+str(i+1)+"</th>\
        #                    <td>"+entity.name+"</td>\
        #                    <td>"+str(entity.frequency)+"</td>\
        #                    <td style=\"text-align: center;\">\
        #                        <div style=\"margin-bottom: 5px;\" class=\"badge badge-"+label2+"\">"+label+"</div>\
        #                        <div class=\"progress\">\
        #                            <div class=\"progress-bar\" role=\"progressbar\" style=\"width: "+str(scorePercentage)+"%;background-color: "+rgb+" !important;\"></div>\
        #                        </div>\
        #                    </td>\
        #                </tr>"
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


    #todo: error checks
    htmlTemplateFile = open(get_app_path()+"/res/survey_template.html", 'r')
    htmlString = htmlTemplateFile.read()
    htmlTemplateFile.close()

    rows = ""
    entities = getMergedEntities()#sorted(list(userData.entities.values()), key=lambda x: x.frequency, reverse=True)

    for i, entity in enumerate(entities):
        scorePercentage = round((entity.score+1.0)/2.0*100)
        label = "Positive" if entity.score > 0.15 else ("Negative" if entity.score < -0.15 else "Neutral")
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



        #rowStr = '<tr>\
        #                    <td>'+'<div class="form-check"><input type="checkbox" class="form-check-input" id="exampleCheck1"></div>'+'</td>\
        #                    <td>'+entity.name+'</td>\
        #<td style = "text-align: center;"> <div> <span class ="badge" style="background-color: ' + color + '"> ' + label + ' </span> <br> <br> <input type="range" min="0" max="100" value="' + str(scorePercentage) + '" step="1" class ="range" onload="updateTextInput(this);" oninput="updateTextInput(this);"/> </div> </td>\
        #                </tr>'
        #with the view
        rowStr ='<tr class="entityRow">' \
                '<th scope="row">' + str(i + 1) + '</th>'\
                '<td>' + entity.name + '</td>' \
                '<td style = "text-align: center;">'+' <div> <span class ="badge" style="background-color: ' + color + '"> ' + label + ' </span> <br> <br> <input type="range" min="0" max="100" value="' + str(scorePercentage) + '" step="1" class ="range" onload="updateTextInput(this);" oninput="updateTextInput(this);" style="pointer-events: none;" disabled/> </div> </td>' \
                '<td><div class="radio"><label><input class = "inputRad" type="radio" value = "A" name="rad'+str(i)+'" onchange="radioEvent(this);"> Agree</label></div>' \
                '<div class="radio"><label><input class = "inputRad" type="radio" value = "B" name="rad'+str(i)+'" onchange="radioEvent(this);"> Disagree (Please correct it)</label></div>' \
                '<div class="radio"><label><input class = "inputRad" type="radio" value = "C" name="rad'+str(i)+'" onchange="radioEvent(this);"> Don\'t care about entity</label></div></td>' \
                '<td style = "text-align: center;">' + ' <div class="customCorrection" style = "visibility: hidden;"> <span class ="badge" style="background-color: ' + color + '"> ' + label + ' </span> <br> <br> <input type="range" min="0" max="100" value="' + str(scorePercentage) + '" step="1" list="steplist" class ="range round" onload="updateTextInput(this);" oninput="updateTextInput(this);"/> <datalist id="steplist"><option>10</option><option>30</option><option>50</option><option>70</option><option>90</option></datalist> </div> </td>' \
                '</tr>'
        rows += rowStr

    htmlString = htmlString.replace("$ROWS", rows)
    indexFile = open(SURVEY, "wb")
    indexFile.write(htmlString.encode('utf8',errors="ignore"))
    indexFile.close()

def runServer():
    print("******************************************B " + str(threading.get_ident()))
    #server = socketserver.TCPServer(('localhost', 0), MyRequestHandler)
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
    try:
        copyfile(finalPath, HOME_PATH + "/history.db") #todo. Will this fail if can't overwrite.
    except:
        log("ERROR COPYING HISTORY FILE FROM CHROME USING: "+str(finalPath))
        log("Here is a list of chrome directory: "+str(os.listdir(path)))
        os._exit(1)
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
        if finalDomain.endswith(domain):
            return True
    return False

def refresh():
    global old_time, last_process_time, is_sleeping, count
    if old_time != None and time.time() - old_time < 60*60:
        print("Skip because sleeping.")
        return

    print("******************************************refresh" + str(threading.get_ident()))
    log("Refresh")
    is_sleeping = False
    last_process_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    global userData
    #copyfile("/Users/rich/Library/Application Support/Google/Chrome/Default/" + CHROME_HISTORY_SQLITE_FILE, HOME_PATH+"/history.db")
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
    query = "SELECT urls.url, urls.visit_count FROM urls, visits WHERE urls.id = visits.url;"
    cursor.execute(query)
    links = set([row[0] for row in cursor.fetchall()])
    db.close()
    log("Extracted links from chrome db.")
    for link in links:
        linkData = parse.urlsplit(link)
        if linkData == None or linkData.hostname == None:
            log("Skip, missing data for: "+str(link))
            continue
        hostname = linkData.hostname.lower()
        hostnameTrim = hostname[len("www."):] if hostname.startswith("www.") else hostname
        if isBlacklisted(hostnameTrim):
            #print("BLACKLISTED "+linkData.hostname.lower())
            continue
        if link.lower() in userData.urls:
            continue
        userData.urls[link.lower()] = UserDataURL(link, False)

    count = 0
    log("Links pre-processed.")
    updateFrontend()



    #Time to process
    for key,url in userData.urls.items():
        if url.processed:
            #print("skip")
            continue

        if count%4 == 0:
            updateFrontend()
            save()
        if count >= 100:
            break #todo: limit extractions to 100 per rest.


        time.sleep(random.randint(15, 30))


        try:
            #print("processing")
            article = Article(url.url)
            article.download()
            article.parse()
            document = article.title+"\n"+article.text
            url.processed = True
            count += 1
            entitySentiments = entitySentimentAnalyzer.analyze(document)[:5] #todo: We pick top 5 from article. Better to use title for advantage.!
            for entitySentiment in entitySentiments:
                nameKey = entitySentiment.name.lower()
                bucketScore = float(-1.0 if entitySentiment.score < NEUTRAL_THRESHOLD_LOWER else (1.0 if entitySentiment.score > NEUTRAL_THRESHOLD_UPPER else 0.0))

                if nameKey in userData.entities:
                    userEntity = userData.entities[nameKey]
                    userEntity.score = (userEntity.score * userEntity.frequency + bucketScore) / float(userEntity.frequency + 1)
                    userEntity.frequency += 1
                else:
                    userData.entities[nameKey] = UserDataEntity(entitySentiment.name, bucketScore, 1)


            n = 9
        except Exception as e:
            log('Skip article processing due to Error: ' + str(e))
            continue

    is_sleeping = True
    updateFrontend()
    save()
    log("Done refreshing. Sleeping for 1 hour")

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
    if not isinstance(port, int):
        raise ValueError('Invalid port')
    log("Open Browser with available: "+str(webbrowser._browsers))
    url = "http://localhost:"+str(port)
    try:
        if not webbrowser.get('open -a /Applications/Google\ Chrome.app %s').open(url):
            log("Error opening chrome browser. Trying generic.")
            webbrowser.open(url)
    except:
        log("Error opening browser. Trying again with generic.")
        webbrowser.open(url)


def button_action():
    print("******************************************action " + str(threading.get_ident()))
    openBrowser(port)

def initGUI():
    log("Init GUI")
    window = Tk()

    window.title("Privacy Project User Study")
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