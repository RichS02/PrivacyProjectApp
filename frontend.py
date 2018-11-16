#todo Move all dynamic frontend here.
from urllib import parse

def top_alert():
    html = '<div class="alert alert-danger" role="alert"><strong>REMINDER!</strong> You have a survey due. Please complete it by today or as soon as possible.</div>'
    return html

def popoverWithLinks(links,i):
    html = ''
    html_start = '<br><br><a class="btn btn-primary btn-sm" tabindex="0" data-toggle="popover" data-popover-content="#pop'+str(i)+'" data-placement="right">View Links</a>\
    <div id="pop'+str(i)+'" style="display: none">\
    <div class="popover-heading">Entity History Links <span style="float:right;cursor:pointer;" data-toggle="popover"></span></div>\
    <div class="popover-body">\
    <div style = "height:200px;overflow:auto;">\
    <table class="table" style="table-layout: fixed;word-wrap: break-word;">\
    <thead>\
    <tr>\
      <th style="width:20%" scope="col">#</th>\
      <th style="width:80%" scope="col">Link</th>\
    </tr>\
    </thead>\
    <tbody>'
    html += html_start
    for j,link in enumerate(links):

        linkData = parse.urlsplit(link)
        if linkData == None or linkData.hostname == None:
            hostnameTrim = "Link"
        else:
            hostname = linkData.hostname.lower()
            hostnameTrim = hostname[len("www."):] if hostname.startswith("www.") else hostname
        html_link = '<a href="'+link+'" target="_blank">'+hostnameTrim+'</a>'
        html_row = '<tr>\
              <th scope="row">'+str(j+1)+'</th>\
              <td>'+html_link+'</td>\
            </tr>'
        html += html_row


    html_end = '</tbody>\
    </table>\
    </div>\
    </div>\
    </div>'
    html += html_end
    return html