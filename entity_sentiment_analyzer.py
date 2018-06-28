# NOTE: This version of the EntitySentimentAnalyzer is a lighter version designed for end-users. For the full version
# see the EntitySentimentAnalyzer project on github.

# * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *
# This is the entity sentiment analyzer. It combines named entity recognition (NER) with sentiment analysis systems.
# The primary algorithm is the 'analyze' function which takes in text (a document) and outputs the entities detected
# in the document along with the sentiment score of each entity. The algorithm is divided into 4 phases:
# (1) Tokenization, (2) Entity Extraction, (3) Entity merging (i.e. unifying entity names into a single name), and
# (4) Sentiment Analysis. Currently we use Stanford NER for entity recognition and Python NLTK for Sentiment analysis.
# though these settings can be changed below. This file is the place to apply any additional NLP techniques to improve
# the combination of NER and Sentiment Analysis. The current algorithm is somewhat naive in the sense that sentiment
# scores are applied to an entity by running sentiment analysis on each text at the position of the entity occurrence.
# * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *

import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import copy

class SentimentSystems:
    NLTK, AFINN, STANFORD = range(3)

class NERSystems:
    NLTK, STANFORD = range(2)


class EntityType:
    PERSON, ORGANIZATION = range(2)


class EntitySentiment:
    def __init__(self, name, type):
        self.name = name
        self.score = None
        self.type = type
        # Note: 'set' so no double counting entities.
        self.sentenceIndexesSet = set()
        self.scoresAtSentenceIndices = {}
        self.dataAtSentenceIndices = {}
        self.frequency = 0
        self.inTitle = False
        self.titleIndex = None


    def getLastName(self):
        split = self.name.split()
        if len(split) == 0:
            return ''
        return split[-1].strip().lower()
    def getFirstName(self):
        split = self.name.split()
        if len(split) == 0:
            return ''
        return split[0].strip().lower()


class EntitySentimentAnalyzer:
    """
    A class that combines sentiment analysis with named entity recognition to produce sentiments for the top
    entities detected.
    """

    def __init__(self):

        #Configure the sentiment and NER systems here.
        self.SENTIMENT_SYSTEM_TYPE = SentimentSystems.NLTK
        self.NER_SYSTEM_TYPE = NERSystems.NLTK
        self.sentimentSystem = SentimentIntensityAnalyzer()


    #The entity sentiment algorithm. Takes in a single article and returns the average sentiment for each entity
    #across the entire article. Remember it is per-article so if one article has more positive mentions than another
    #it doesn't matter. An example of what this means: You read 5 articles about Obama. The first has 1000 positive
    #sentiments about Obama and returns an avg score of 1. The remaining articles all only have a few negative mentions
    #and returns avg score of say -1. Overall the profile is NEGATIVE for Obama because the user read more negative
    #articles, even though the user has seen drastically more positive sentiments.
    def analyze(self, text):


        # ******** Phase 1/2 - Tokenize the document and then extract entities. ********

        # Old command tool NER
        #tagged_sentences = self.nerTagger.tag_sents([nltk.word_tokenize(s) for s in sentences])
        #entities_sentences = [self.parseEntities(tags) for tags in tagged_sentences]

        # Regardless of the NER system chosen, these must have the same format.
        entities_sentences, sentences = None, None

        if self.NER_SYSTEM_TYPE == NERSystems.STANFORD:
            text = text.replace("\n", " . ").strip()
            # Tokenization handled by Stanford NER.
            # Get the entities and sentences from NER.
            # See stanford_ner_wrapper.py for more info.
            entities_sentences, sentences = self.nerTagger.tagSentences(text)
        elif self.NER_SYSTEM_TYPE == NERSystems.NLTK:
            # Tokenize the document.
            paragraphs = text.split('\n')
            sentences = []
            for paragraph in paragraphs:
                paragraphStrip = paragraph.strip()
                if paragraphStrip == '':
                    continue
                else:
                    sentences.extend(nltk.sent_tokenize(paragraphStrip))
            # Then get the entities.
            tagged_sentences = [nltk.pos_tag(sentence) for sentence in [nltk.word_tokenize(s) for s in sentences]]
            chunks = nltk.ne_chunk_sents(tagged_sentences, binary=False)
            entities_sentences = []
            for chunk_sent in chunks:
                entities_sentences.append([])
                for chunk in chunk_sent:
                    if hasattr(chunk, 'label') and (chunk.label() == "PERSON" or chunk.label() == "ORGANIZATION"):
                        entities_sentences[-1].append((' '.join(c[0] for c in chunk),chunk.label()))


        entityTable = {}
        first = True
        for index, entities in enumerate(entities_sentences):
            if len(entities) == 0:
                continue
            #if len(focusEntities) == 0:
                #print('NO FOCUS ENTITY FOR: ' + sentences[index])
            for entity, type in entities:
                entityLower = entity.strip().lower()
                if entityLower in entityTable:
                    entityTable[entityLower].frequency += 1
                    entityTable[entityLower].sentenceIndexesSet.add(index)
                else:
                    entitySentiment = EntitySentiment(entity.strip(), type)
                    entitySentiment.frequency = 1 if not first else 3
                    entitySentiment.inTitle = True if first else False
                    entitySentiment.titleIndex = index if first else None
                    entitySentiment.sentenceIndexesSet.add(index)
                    entityTable[entityLower] = entitySentiment
            #if first:
                #print("FIRST")
                #print(str(entities))
            first = False


        # ******** Phase 3 - Resolve entities. ********


        self.mergeEntities(entityTable)

        topEntities = list(entityTable.values())
        topEntities.sort(key=lambda e: e.frequency, reverse=True)


        # ******** Phase 4 - Sentiment Analysis. ********

        for topEntity in topEntities:
            total = 0
            count = 0
            score = None
            for i in topEntity.sentenceIndexesSet:
                #Performances poorly on our dataset.
                #if self.SENTIMENT_SYSTEM_TYPE == SentimentSystems.STANFORD:
                    #output = self.sentimentSystem.annotate(sentences[i], properties={
                    #    'annotators': 'sentiment',
                    #    'outputFormat': 'json'
                    #})
                    #outputSentence = output['sentences'][0]
                    #sentimentValue = int(outputSentence['sentimentValue'])
                    #print("VALUE: "+ str(sentimentValue) +' ' + str(outputSentence['sentiment']) + ' '+sentences[sentenceIndex])


                if self.SENTIMENT_SYSTEM_TYPE == SentimentSystems.NLTK:
                    output = self.sentimentSystem.polarity_scores(sentences[i])
                    sentimentValue = output['compound']

                    #Todo: Experimental
                    if topEntity.inTitle and topEntity.titleIndex == i:
                        #print('Title sentiment of '+topEntity.name + ' is '+str(sentimentValue))
                        if sentimentValue <= -0.4:
                            sentimentValue = -2
                            count += 1

                    #entityProfile[entity].append(output['compound'])
                    #print('SENTIMENT ' + entity + ':' + str(output['compound']) + ' – ' + sentences[sentenceIndex])
                    total += sentimentValue
                    count += 1
                    topEntity.scoresAtSentenceIndices[i] = sentimentValue
                    topEntity.dataAtSentenceIndices[i] = sentences[i]

                #Performs slightly worse than NLTK on our dataset.
                #if self.SENTIMENT_SYSTEM_TYPE == SentimentSystems.AFINN:
                    #scr = self.sentimentSystem.score(sentences[i])


            if count > 0 :
                score = float(total)/float(count)

            topEntity.score = score

        return topEntities


    # Fix edge case: Obama is detected but not Barack Obama. But Michelle Obama is detected. You've just lost Obama.
    # Similarly: {'george w. bush': 2, 'jeb bush': 1, 'ivy ziedrich': 1, 'bush': 16, ... } if Jeb was 3 here then he would be the top entity. Maybe don't merge at all? But then
    # you would have "bush' as a category and it would include both articles focusing on george w bush and jeb bush. Perhaps pick first, title and or use additonal NLP techniques.
    # Merge fist names AFTER trying to merge last names. For example if you still have single names leftover that couldn't be matched, most likely a first name of an entity.
    # This is important for Hillary Clinton.
    def mergeEntities(self,entityTable):
        entityTableCopy = copy.deepcopy(entityTable) #Very important to use copy to prevent double counting merges.
        entitiesToRemove = []
        for name1, value1 in entityTableCopy.items():
            splitName = value1.name.split()

            matched = False
            for name2, value2 in entityTableCopy.items():
                if name1 == name2:
                    continue  # skip matching key names.

                #Match single names to last names.
                if len(splitName) == 1 and splitName[0].strip().lower() == value2.getLastName():
                    entityTable[name2].frequency += entityTableCopy[name1].frequency
                    if entityTableCopy[name1].inTitle:
                        entityTable[name2].inTitle = entityTableCopy[name1].inTitle
                    entityTable[name2].sentenceIndexesSet = entityTableCopy[name2].sentenceIndexesSet.union(entityTableCopy[name1].sentenceIndexesSet)
                    #entityTable[name2] = entityTable[name2] + entityTable[name1]
                    #print('MERGED: ' + name1 + ' TO ' + name2)
                    matched = True

                # Match single names to first names.
                if len(splitName) == 1 and splitName[0].strip().lower() == value2.getFirstName():
                    entityTable[name2].frequency += entityTableCopy[name1].frequency
                    if entityTableCopy[name1].inTitle:
                        entityTable[name2].inTitle = entityTableCopy[name1].inTitle
                    entityTable[name2].sentenceIndexesSet = entityTableCopy[name2].sentenceIndexesSet.union(entityTableCopy[name1].sentenceIndexesSet)
                    #entityTable[name2] = entityTable[name2] + entityTable[name1]
                    #print('MERGED: ' + name1 + ' TO ' + name2)
                    matched = True

                # Match first and last names to first and last names. i.e. George Bush --> George ..... Bush
                if len(splitName) == 2 and (len(value2.name.split()) >= 3 and splitName[0].strip().lower() == value2.getFirstName() and splitName[1].strip().lower() == value2.getLastName()) :
                    entityTable[name2].frequency += entityTableCopy[name1].frequency
                    if entityTableCopy[name1].inTitle:
                        entityTable[name2].inTitle = entityTableCopy[name1].inTitle
                    entityTable[name2].sentenceIndexesSet = entityTableCopy[name2].sentenceIndexesSet.union(entityTableCopy[name1].sentenceIndexesSet)
                    # entityTable[name2] = entityTable[name2] + entityTable[name1]
                    # print('MERGED: ' + name1 + ' TO ' + name2)
                    matched = True

            if matched:
                entitiesToRemove.append(name1)  # currently match single names to ALL last names/first names.  We then delete it after done matching all.

        for r in entitiesToRemove:
            entityTable.pop(r, None)
        #DON'T remove because when you incorrectly match there will be no single names to fallback on the test. See Michelle Obama case in ObamaPos7.txt


    #End any sub-processes or cleanup resources if needed.
    def end(self):
        return