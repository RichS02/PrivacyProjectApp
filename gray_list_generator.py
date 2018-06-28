# Just a tool to generate the gray_list.csv file. This file itself, along with the gray_list_generator_resources, are
# not required in the packaged application. Only the gray_list.csv file is necessary.

import csv
import os
import blacklists

PATH_SOURCES = "gray_list_generator_resources/Top-100-Sources"
PATH_ADDITIONS = "gray_list_generator_resources/manual-additions.csv"
outputFile = open('res/gray_list.csv', 'w', encoding='UTF-8')

additions_file = open(PATH_ADDITIONS, 'r', encoding='UTF-8')
additions_reader = csv.reader(additions_file)
additions = [x[0] for x in list(additions_reader) if len(x) > 0]
sources = {}

for a in additions:
    sources[a] = 1

def stripTopLevel(host):
    finalDomain = ""
    parts = host.split(".")
    if len(parts) <= 1:
        raise ValueError("No top level to remove.")
    elif len(parts) == 2:
        return parts[0]

    isDouble = False
    for doubleSuffix in blacklists.SUFFIX_WHITELIST_TWO:
        if host.endswith(doubleSuffix):
            isDouble = True
            break

    if isDouble:
        finalDomain = ".".join(parts[:-2])
    else:
        finalDomain = ".".join(parts[:-1])

    return finalDomain




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

w = csv.writer(outputFile)

for file in os.listdir(os.fsencode(PATH_SOURCES)):
    filename = os.fsdecode(file)
    if filename.endswith(".csv"):
        with open(PATH_SOURCES+"/"+filename, 'r', encoding='UTF-8') as file:
            r = csv.reader(file)
            for i,row in enumerate(r):
                if i < 6 or isBlacklisted(row[0]) or float(row[1])<5.0:
                    continue
                if i == 6:
                    sources[row[0]] = 1
                else:
                    if row[0] not in sources:
                        sources[row[0]] = 0
        continue
    else:
        continue

items = list(sources.items())
items.sort(key=lambda tup: tup[1], reverse=True)
for k,v in items:
    w.writerow([stripTopLevel(k),''])

outputFile.close()
additions_file.close()