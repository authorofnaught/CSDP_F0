#!/opt/local/bin/python

import os
from os.path import join

import cProfile
import codecs
import shutil

from pyacoustics.utilities import utils

from pyacoustics.textgrids import textgrids
from pyacoustics.speech_rate import uwe_sr
from pyacoustics.speech_rate import dictionary_estimate
from pyacoustics.signals import audio_scripts
from pyacoustics.intensity_and_pitch import praat_pi
from pyacoustics import aggregate_features

import praatio

import general_CSDP_MCRP


def justPitch(inputPath, outputPath):
    utils.makeDir(outputPath)
    
    for fn in utils.findFiles(inputPath, filterExt=".txt"):
        valList = utils.openCSV(inputPath, fn, valueIndex=1)
        
        newValList = []
        for val in valList:
            try:
                val = str(float(val))
            except ValueError:
                val = "0.0"
            newValList.append(val)
        
        open(join(outputPath, fn), "w").write("\n".join(newValList) + "\n")
        
        
def correctTextgrids(inputDir, outputDir, correctDictFullPath):
    
    utils.makeDir(outputDir)
    
    correctDictPath, correctDictFN = os.path.split(correctDictFullPath)
    tmpDataList = utils.openCSV(correctDictPath, correctDictFN)
    wordReplaceDict = {row[0]:row[1] for row in tmpDataList}
    
    z = 0
    for fn in utils.findFiles(inputDir, filterExt=".TextGrid"):
        print fn
        tg = praatio.openTextGrid(join(inputDir, fn))
        tier = tg.tierDict["Mother"]
        
        newEntryList = []
        for start, stop, label in tier.entryList:

            label = _filterLabelFunction(label)
            
            wordList = []
            for word in label.split(" "):
                word = word.strip()
                if word == "":
                    continue
                try:
                    newWord = wordReplaceDict[word]
                    print z, word, newWord
                    z += 1
                    word = newWord
                except KeyError:
                    pass # No change
                wordList.append(word)
            newLabel = " ".join(wordList)
            newEntryList.append( (start, stop, newLabel) )
        
        tg.replaceTier("Mother", newEntryList)
        tg.save(join(outputDir, fn))


def _filterLabelFunction(label):
    label = label.lower()
    
    # Strip punctuation
    # 'nc' - 'not comprehensible'?
    for char in ['.', '!', '?', ',', "' ", " '", ';', ',', '--', 'nc', '(nc)', '`']:
        label = label.replace(char, ' ')
    
    label = label.replace('(', '<')
    label = label.replace(')', '>')
    
    # Strip speech mode labels
    for mode in ['<whispers>', '<whispering>', '<whispered>', 
                 '<sad voice>', '<normal>', 
                 '<laughing>', '<laughter>']:
        label = label.replace(mode, ' ')

    # Remove any general mode that contains 'voice' e.g. 'normal voice'
    for subLabel in ['voice',]:
        label = _matchDemarker(label, '<', '>', subLabel)  

    # Remove specific tags (each one only occurs once)
    for subLabel in ['<mika presumably short for mikayla>',
                 "<the why don't ya is extremely slurred>",
                 "<back to normal>",
                 "<this was said very slurred>",
                 "<not sure if correct>",]:
        label = label.replace(subLabel, ' ')
        
    label = label.strip()
    
    for startMarker, endMarker in [('[', ']')]:
        label = _matchDemarker(label, startMarker, endMarker)
    
    # If any < > tag is still in the label, wipe the label
    # it may represent some portion of the text that was not correctly
    # transcribed or untranscribable--such as laughter or onomatopoeia
    if '<' in label:
        start = label.index('<')
        end = label.index('>')
        
        label = label[:start] + label[end+1:]

    return label


def _matchDemarker(label, startMarker, endMarker, subLabel=None):
    
    startIndex = 0

    while True:
#         print startIndex
        try:
            startIndex = label.index(startMarker, startIndex)
        except ValueError:
            break
        
        endIndex = label.index(endMarker, startIndex)
    
        if subLabel == None or subLabel in label[startIndex:endIndex]:
            label = label[:startIndex] + label[endIndex+1:]
        else:
            label = label
            startIndex = endIndex
    
    return label


def mergePlayTextgrids(origTGPath, laughterTGPath, outputPath):
    
    utils.makeDir(outputPath)
    
    speechTierName = "Mother"
    laughTierName = "Mother's Backchannel"
    
    for fn in utils.findFiles(origTGPath, filterExt=".TextGrid"):
        if os.path.exists(join(outputPath, fn)):
            continue
        print fn
        origTG = praatio.openTextGrid(join(origTGPath, fn))
        laughTG = praatio.openTextGrid(join(laughterTGPath, fn))
        
        origSpeechTier = origTG.tierDict[speechTierName]
        origLaughTier = origTG.tierDict[laughTierName]
        
        laughEntryList = laughTG.tierDict[laughTierName].find("LA")
        laughSpeechTier = laughTG.tierDict[speechTierName]
        
        for start, stop, label in laughEntryList:
            origLaughTier.insert((start, stop, label), warnFlag=True,
                                 collisionCode="replace")
            
            origSpeechMatches = origSpeechTier.getEntries(start, stop, boundaryInclusive=True)
            laughSpeechMatches = []
            for entry in origSpeechMatches:
                origSpeechTier.deleteEntry(entry)
                
                subStart, subStop, subLabel = entry
                laughSpeechMatches.extend(laughSpeechTier.getEntries(subStart, subStop, boundaryInclusive=True))
            laughSpeechMatch = set(laughSpeechMatches)
            for entry in laughSpeechMatches:
                origSpeechTier.insert(entry, warnFlag=True, collisionCode="replace")
            
#             # Need to delete any possible matches from the orig textgrids
#             if len(laughSpeechMatches) == 0:
#                 origSpeechMatches = origSpeechTier.getEntries(start, stop, boundaryInclusive=True)
#                 for entry in origSpeechMatches:
#                     origSpeechTier.delete(entry)
#             
#             # Need to replace the entries in the origSpeechTier with those in
#             # the laughSpeechTier
#             else:
#                 for entry in laughSpeechMatches:
#                     origSpeechTier.insert(entry, 
#                                           warnFlag=True, 
#                                           collisionCode="replace")
        
        origTG.replaceTier(speechTierName, origSpeechTier.entryList)
        origTG.replaceTier(laughTierName, origLaughTier.entryList)
        origTG.save(join(outputPath, fn))
        

# Combines information in the textgrids with laughter checks with the 
# original textgrids
# mergePlayTextgrids(join(path, "textgrids_no_laughter_check"),
#                        join(path, "textgrids_just_laughter"),
#                        join(path, "textgrids_after_laughter_merge"))
 
# Spellchecks textgrids
# correctTextgrids(join(path, "textgrids"), 
#                      join(path, "textgrids_intervals_marked"), 
#                      join("/Users/tmahrt/Desktop/experiments/Mother_Prosody_RAship/all_data", 
#                           "play_session_pronunciation_output.csv"), 
#                      )
        
def playTask_step1(path):

    # Generates a series of textgrid files that have been cleaned and
    # with the mother's speech isolated from room noise and child speech
    general_CSDP_MCRP.generateEpochFiles(join(path, "textgrids_intervals_marked"),
                                         join(path, "wavs"),
                                         join(path, "epochs")
                                         )


    general_CSDP_MCRP.processTextgrids(path, "textgrids_intervals_marked", 
#                                 includeMothersPhones=True)
                                 )

    general_CSDP_MCRP.simplifyTextgrids(join(path, "textgrids_w_epochs_filtered_for_child_speech"),
                                    join(path, "textgrids_w_epochs_filtered_for_child_speech_two_label")
                                    )
 
    general_CSDP_MCRP.simplifyTextgrids(join(path, "textgrids_w_epochs_filtered_for_room_noise"),
                                    join(path, "textgrids_w_epochs_filtered_for_room_noise_two_label")
                                    )
    general_CSDP_MCRP.simplifyTextgrids(join(path, "textgrids_w_epochs_final_non_isolated"),
                                   join(path, "textgrids_w_epochs_final_non_isolated_two_label")
                                   )


    # Extract the wav segments and textgrids for the individual segments
    # --we'll extract the speech rate from each of these segments individually
    general_CSDP_MCRP.extractMotherSpeech(join(path, "wavs"),
                                     join(path, "textgrids_w_epochs_final_isolated"),
                                     "Mother",
                                     join(path, "wavs_subset_mothers_speech"),
                                     join(path, "textgrids_subset_mothers_speech"))

    # Prepare the directory for the data extracted by the matlab script
    utils.makeDir(join(path, "uwe_raw_speech_rate_mothers_speech"))


def playTask_step3(path, islevPath, praatScriptPath, praatExePath):

    # Acoustic analysis
    # (must have run extractSpeechRate() in matlab first)   
    uwe_sr.aggregateSpeechRate(join(path, "tg_info"), 
                               join(path, "uwe_raw_speech_rate_mothers_speech"), 
                               join(path, "uwe_nucleus_listing_mothers_speech"), 
                               44100)
    uwe_sr.uwePhoneCountForEpochs(join(path, "epochs"), 
                                  join(path, "tg_info"),
                                  join(path, "uwe_nucleus_listing_mothers_speech"), 
                                  join(path, "uwe_speech_rate_for_epochs"))
   
#    dictionary_estimate.manualPhoneCount(join(path, "tg_info"),
#                                         islevPath,
#                                         join(path, "manual_phone_counts"),
#                                         [u'(pST)', u'(nST)'])
     
#    dictionary_estimate.manualPhoneCountForEpochs(join(path, "manual_phone_counts"),
#                                                  join(path, "tg_info"),
#                                                  join(path, "epochs"),
#                                                  join(path, "manual_phone_counts_for_epochs"))

    # The follow code can be run over the whole audio files, regardless of epoch
    # or textgrids (we'll extract pitch information for the intervals and
    # epochs later) 
    utils.makeDir(join(path, "praat_f0_min_75_max_750"))
    for fn in utils.findFiles(join(path, "wavs"), filterExt=".wav",
                              skipIfNameInList=utils.findFiles(join(path, "praat_f0_min_75_max_750"), filterExt=".txt")):
        print fn
        praat_pi.getPraatPitchAndIntensity(inputPath=join(path, "wavs"), 
                                           inputFN=fn, 
                                           outputPath=join(path, "praat_f0_min_75_max_750"), 
                                           praatEXE=praatExePath, 
                                           praatScriptPath=praatScriptPath, 
                                           minPitch=75, 
                                           maxPitch=750, 
                                           sampleStep=0.01, 
                                           forceRegenerate=True)
 
    praat_pi.medianFilter(join(path, "praat_f0_min_75_max_750"), 
                          join(path, "praat_f0_75_750_median_filtered_9"), 
                          windowSize=9)
    # END whole audio file pitch extraction

    general_CSDP_MCRP.extractPraatPitchForEpochs(join(path, "praat_f0_75_750_median_filtered_9"),
                                            join(path, "epochs"),
                                            join(path, "tg_info"),
                                            join(path, "praat_f0_75_750_median_filtered_9_for_epochs")
                                            )

    general_CSDP_MCRP.eventStructurePerEpoch(join(path, "epochs"),
                                        join(path, "textgrids_two_tags"),
                                        join(path, "textgrids_w_epochs_filtered_for_child_speech_two_label"),
                                        join(path, "textgrids_w_epochs_filtered_for_room_noise_two_label"),
                                        join(path, "textgrids_w_epochs_final_non_isolated_two_label"),
                                        join(path, "event_frequency_and_duration"),
                                        "Mother",
                                        "Mother's Backchannel")

    general_CSDP_MCRP.generateEpochRowHeader(join(path, "epochs"),
                                        join(path, "epoch_row_header"),
                                        "P")

    headerStr = ("file,id,session,interval,int_start,int_end,int_dur,"
                 "ms_dur_s,ms_freq,ms_child_speech_filtered_dur_s,"
                 "ms_noise_filtered_dur_s,ms_full_dur_s,lost_ms_dur_s,"
                 "fp_dur_s,fp_freq,la_dur_s,la_freq,"
#                 "dict_sylcnt,"
#                 "dict_phncnt,dict_speech_dur,
                 "uwe_sylcnt,f0_mean,"
                 "f0_max,f0_min,f0_range,f0_var,f0_std"
                 )
    aggregate_features.aggregateFeatures(path, ["epoch_row_header", 
                                                "event_frequency_and_duration", 
 #                                               "manual_phone_counts_for_epochs",
                                                "uwe_speech_rate_for_epochs", 
                                                "praat_f0_75_750_median_filtered_9_for_epochs"],
                                         headerStr
                                         )


def playTask_F0Compare(path):

    # Copy F0 Check tier from edited textgrid to the origin textgrid
    for fn in utils.findFiles(join(path, "textgrids_f0_checks"), 
                              filterExt=".TextGrid"):
        tg = praatio.openTextGrid(join(path, "textgrids_f0_checks", fn))
        tier = tg.tierDict["F0 Checks"]
    
        tg = praatio.openTextGrid(join(path, "textgrids_intervals_marked", fn))
        if "F0 Checks" not in tg.tierDict.keys():
            tg.addTier(tier)
            tg.save(join(path, "textgrids_intervals_marked", fn))

    # Generates a series of textgrid files that have been cleaned and
    # with the mother's speech isolated from room noise and child speech
            #     general_CSDP_MCRP.processTextgrids(path, "textgrids_intervals_marked", 
            #                                   includeMothersPhones=True)
            # 
            #     general_CSDP_MCRP.simplifyTextgrids(join(path, "textgrids_w_epochs_filtered_for_child_speech"),
            #                                    join(path, "textgrids_w_epochs_filtered_for_child_speech_two_label")
            #                                    )
            #      
            #     general_CSDP_MCRP.simplifyTextgrids(join(path, "textgrids_w_epochs_filtered_for_room_noise"),
            #                                    join(path, "textgrids_w_epochs_filtered_for_room_noise_two_label")
            #                                    )
            #     general_CSDP_MCRP.simplifyTextgrids(join(path, "textgrids_w_epochs_final_non_isolated"),
            #                                    join(path, "textgrids_w_epochs_final_non_isolated_two_label")
            #                                    )
            #     
            #     general_CSDP_MCRP.simplifyTextgrids(join(path, "textgrids_w_epochs_filtered_for_room_noise_child_speech_and_f0_checks"),
            #                                    join(path, "textgrids_w_epochs_filtered_for_room_noise_child_speech_and_f0_checks_two_label")
            #                                    )



#  
#     # Extract the wav segments and textgrids for the individual segments
#     # --we'll extract the speech rate from each of these segments individually
#     general_CSDP_MCRP.extractMotherSpeech(join(path, "wavs"),
#                                      join(path, "textgrids_w_epochs_final_isolated"),
#                                      "Mother",
#                                      join(path, "wavs_subset_mothers_speech"),
#                                      join(path, "textgrids_subset_mothers_speech"))

    

    # Acoustic analysis
    # (go run     
#     uwe_sr.aggregateSpeechRate(join(path, "tg_info"), 
#                                join(path, "uwe_raw_speech_rate_mothers_speech"), 
#                                join(path, "uwe_nucleus_listing_mothers_speech"), 
#                                44100)
#     uwe_sr.uwePhoneCountForEpochs(join(path, "epochs"), 
#                                   join(path, "tg_info"),
#                                   join(path, "uwe_nucleus_listing_mothers_speech"), 
#                                   join(path, "uwe_speech_rate_for_epochs"))
#   
#     dictionary_estimate.manualPhoneCount(join(path, "tg_info"),
#                                          join("/Users/tmahrt/Dropbox/workspace/pysle/test/islev2.txt"),
#                                          join(path, "manual_phone_counts"),
#                                          [u'(pST)', u'(nST)'])
#     cProfile.run("""dictionary_estimate.manualPhoneCount("/Users/tmahrt/Desktop/experiments/Mother_Prosody_RAship/all_data/play/tg_info",
#                                            "/Users/tmahrt/Dropbox/workspace/pysle/test/islev2.txt",
#                                            "/Users/tmahrt/Desktop/experiments/Mother_Prosody_RAship/all_data/play/manual_phone_counts")""")
     
#     dictionary_estimate.manualPhoneCountForEpochs(join(path, "manual_phone_counts"),
#                                                   join(path, "tg_info"),
#                                                   join(path, "epochs"),
#                                                   join(path, "manual_phone_counts_for_epochs"))

    # The follow code can be run over the whole audio files, regardless of epoch
    # or textgrids (we'll extract pitch information for the intervals and
    # epochs later) 
#     for fn in utils.findFiles(join(path, "wavs"), filterExt=".wav",
#                               skipIfNameInList=utils.findFiles(join(path, "praat_f0_min_75_max_750"), filterExt=".txt")):
#         print fn
#         praat_pi.getPraatPitchAndIntensity(inputPath=join(path, "wavs"), 
#                                            inputFN=fn, 
#                                            outputPath=join(path, "praat_f0_min_75_max_750"), 
#                                            praatEXE="/Applications/praat.App/Contents/MacOS/Praat", 
#                                            praatScriptPath="/Users/tmahrt/Dropbox/workspace/AcousticFeatureExtractionSuite/praatScripts", 
#                                            minPitch=75, 
#                                            maxPitch=750, 
#                                            sampleStep=0.01, 
#                                            forceRegenerate=True)

#     justPitch(join(path, "praat_f0"),
#               join(path, "praat_just_f0"),
#               )

#     praat_pi.medianFilter(join(path, "praat_f0"), 
#                           join(path, "praat_f0_median_filtered_5"), 
#                           windowSize=5)
# 
# 
#     praat_pi.medianFilter(join(path, "praat_f0_min_75_max_750"), 
#                           join(path, "praat_f0_75_750_median_filtered_9"), 
#                           windowSize=9)

#     praat_pi.medianFilter(join(path, "praat_f0"), 
#                           join(path, "praat_f0_median_filtered_50"), 
#                           windowSize=49)
    # END whole audio file pitch extraction

#    general_CSDP_MCRP.extractPraatPitchForEpochs(join(path, "praat_f0_75_750_median_filtered_9"),
#                                            join(path, "epochs"),
#                                            join(path, "tg_info"),
#                                            join(path, "praat_f0_75_750_median_filtered_9_for_epochs")
#                                            )
# #     
#    general_CSDP_MCRP.eventStructurePerEpoch(join(path, "epochs"),
#                                        join(path, "textgrids_two_tags"),
#                                        join(path, "textgrids_w_epochs_filtered_for_child_speech_two_label"),
#                                        join(path, "textgrids_w_epochs_filtered_for_room_noise_two_label"),
#                                        join(path, "textgrids_w_epochs_final_non_isolated_two_label"),
#                                        join(path, "event_frequency_and_duration"),
#                                        "Mother",
#                                        "Mother's Backchannel")
# # 
#     general_CSDP_MCRP.generateEpochRowHeader(join(path, "epochs"),
#                                         join(path, "epoch_row_header"),
#                                         "P")
# # 
#    headerStr = "file,id,session,interval,int_start,int_end,int_dur,ms_dur_s,ms_freq,ms_child_speech_filtered_dur_s,ms_noise_filtered_dur_s,ms_full_dur_s,lost_ms_dur_s,fp_dur_s,fp_freq,la_dur_s,la_freq,dict_sylcnt,dict_phncnt,dict_speech_dur,uwe_sylcnt,f0_mean,f0_max,f0_min,f0_range,f0_var,f0_std"
#    aggregate_features.aggregateFeatures(path, ["epoch_row_header", 
#                                                "event_frequency_and_duration", 
#                                                "manual_phone_counts_for_epochs",
#                                                "uwe_speech_rate_for_epochs", 
#                                                "praat_f0_75_750_median_filtered_9_for_epochs"],
#                                         headerStr
#                                         )

def deleteBadLaughterMergedFiles(path, featureList):
    '''
    probably don't want to run this ever again
    
#     deleteBadLaughterMergedFiles("/Users/tmahrt/Desktop/experiments/Mother_Prosody_RAship/all_data/play",
#                    ["aggr", "textgrids_w_epochs", "textgrids_two_tags", "textgrids_subset_mothers_speech", 
#                     "event_frequency_and_duration", "pitch_measures_for_epochs",
#                     "textgrids", "tg_info", "uwe_raw_speech_rate", "uwe_speech_rate_for_epochs", "uwe_nucleus_listing_mothers_speech"])
    '''
    affectedIDs = [2,4,5,6,7,8,11,15,17,19,22,30,38,39,43,48,51,56,62,67,68,74,80,86,88,109,119,124]
    
    for feature in featureList:
        
        fn = "CSDP_ID_%03d_P%s"
        
        for id in affectedIDs:
            for ext in [".txt", ".csv", ".TextGrid"]:
                try:
                    os.remove(join(path, feature, fn % (id,ext)))
                    print "Removed: %s" % join(path, feature, fn % (id,ext))
                except OSError:
                    continue
    
    # Remove subwav files
    for feature in [#"wavs_subset_mothers_speech", 
                    "uwe_raw_speech_rate_mothers_speech"]:      
        fnList = utils.findFiles(join(path, feature))
        for fn in fnList:
            idNum = int(fn.split("_")[2])
            if idNum in affectedIDs:
                os.remove(join(path, feature, fn))

def extractUtterances(path):
    
    dict = {"CSDP_ID_001_P":[(126.3, 129),
(196.69, 198.144),
(219.77, 222.27),
(239.65, 240.54),
(271.21, 272.92),
(344.04, 349.01),
(420.83, 427.12),
(465.24, 466.50),
(489.10, 491.09),],
            "CSDP_ID_002_P":[(187.58, 188.83),
(220.48, 223.12),
(228.85, 231.59),
(321.53, 322.75),
(337.84, 339.12),
(371.33, 372.30),
(407.82, 408.67),],
            "CSDP_ID_088_P":[(46.46, 47.41),
(182.27, 182.80),
(199.17, 203.58),
(396.79, 400.55),
                            ]}
    
    for fn in dict.keys():
        for i, tmpTuple in enumerate(dict[fn]):
            startT, endT = tmpTuple
            audio_scripts.extractSubwav(join(path, "wavs", fn+".wav"), 
                                        join(path, "tmp_subwavs", "%s_%d.wav" % (fn, i)), startT, endT, singleChannelFlag=True)
            
            tg = praatio.openTextGrid(join(path, "textgrids", fn+".TextGrid"))
            tgTmp = tg.crop(True, False, startT, endT)
#             tgTmp.entryList = 
            tgTmp = tgTmp.editTimestamps(-1*tgTmp.minTimestamp, -1*tgTmp.minTimestamp, -1*tgTmp.minTimestamp)
            tgTmp.save(join(path, "tmp_subwavs", "%s_%d.TextGrid" % (fn, i)))


def copyFiles():
    
    path = "/Users/tmahrt/Desktop/experiments/Mother_Prosody_RAship/all_data/play"
    outputPath = "/Users/tmahrt/Desktop/experiments/Mother_Prosody_RAship/all_data/play_f0_checks"
    idList = ["012_P", "023_P", "070_P", "109_P", "111_P"]
    import shutil
    
    for folder in utils.findFiles(path, filterPaths=True):
        fnList = utils.findFiles(join(path, folder))
        for id in idList:
            for fn in fnList:
                if id in fn:
                    utils.makeDir(join(outputPath, folder))
                    shutil.copy(join(path, folder, fn),
                                join(outputPath, folder, fn))
                

def guideUser(project_path):
    while True:

        working_directory = raw_input("\nWhat's the name of your working directory within %s\nEnter directory name: " % project_path).strip()
        working_path = join(project_path, working_directory)

        if not os.path.isdir(working_path):
            print('\nHmmm... That directory does not exist in %s.\n'
                  'Please try again or press CTRL+D to exit.\n'
                  'You may to change the "path" variable inside this script.\n' % project_path)
            continue
        else:
            break

    while True:

        step_number = raw_input("\nAre you running step 1 (before Uwe MatLab program) or step 3(after Uwe MatLab program)?\nEnter 1 or 3: ")

        if step_number.strip() == "1":
            while True:
                get_f0_tier = raw_input("\nAs you wish. Running step 1...\n\nDo you want to add tier 'F0 Checks' from textgirds in directory"
                      " 'textgrids_f0_checks' in the same working directory?\nType 'y' or 'n': ")
                if get_f0_tier.strip() == "y":
                    playTask_F0Compare(working_path)
                    print("\nOk. F0 Checks tier added to textgrids in 'textgrids_intervals_marked'.\nMoving on...")
                    break
                elif get_f0_tier.strip() == "n":
                    print("\nOk. Moving on...")
                    break
                else:
                    print('Please enter "y" or "n"')
                    continue
            playTask_step1(working_path)
            stepStr = ("\nStep 1 complete.  Now for step 2...\n\n"
                       "Run the following command in MatLab: \n"
                       "extractSpeechRate('%s', '%s')\n\n"
                       "You'll want to make sure these two files are added to the path:\n"
                       "%s\n"
                       "%s\n\n"
                       "When it is finished, start this program again, and run step 3 over %s\n"
                       )
            print(stepStr % (join(working_path, "wavs_subset_mothers_speech"),
                             join(working_path, "uwe_raw_speech_rate_mothers_speech"),
                             join(project_path, "extractSpeechRate.m"),
                             join(project_path, "nucleus_detection_matlab", "fu_sylncl.m"),
                             working_directory))
            break
        elif step_number.strip() == "3":
            print("\nAs you wish. Running step 3...\n...this might take a bit...\n...and your fan might get loud...\n")
            playTask_step3(working_path,
                           "/Users/authorofnaught/Projects/Maternal_Prosody/islev2.txt",
                           "/Users/authorofnaught/Projects/Maternal_Prosody/AcousticFeatureExtractionSuite/praatScripts",
                           "/Applications/praat.App/Contents/MacOS/Praat",
                           )
            goodbyeString = ("\nOk. Results should have been output to:\n"
                             "%s\n\n"
                             "Have a nice day!\n")
            print(goodbyeString  % (join(working_path, "aggr")))
            break
        else:
            print("\nHmmm... That's not 1 or 3.  Please try again or press CTRL+D to exit.\n")
            continue





if __name__ == "__main__":

    # For "project_path" below, enter the full path of the directory which contains:
    # A) The working directory you plan to use
    # B) the MatLab script "extractSpeechRate.m"
    # C) The directory "nucleus_detection_matlab" which has the script "fu_sylncl.m"
    #
    # The path should be in quotes, for example:
    # project_path = "/Users/authorofnaught/Projects/Maternal_Prosody/"

    project_path = "/Users/authorofnaught/Projects/Maternal_Prosody/results/"
    guideUser(project_path)






