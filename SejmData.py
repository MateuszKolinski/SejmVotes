import urllib.request
import os
import time
import re
import os
import json
from html import unescape
import traceback
from natsort import natsorted
import datetime
import sys
import tika
tika.initVM()
from tika import parser
from os import listdir
from os.path import isfile, join
import roman
import sqlite3
import argparse
import numpy as np

## TO DO
# 1. Bad links
#    https://www.sejm.gov.pl/Sejm9.nsf/agent.xsp?symbol=glosowania&NrKadencji=9&NrPosiedzenia=59&NrGlosowania=187
#    https://www.sejm.gov.pl/Sejm9.nsf/agent.xsp?symbol=glosowania&NrKadencji=9&NrPosiedzenia=33&NrGlosowania=85

# 2. https://orka.sejm.gov.pl/Glos9.nsf/nazwa/34_1/$file/glos_34_1.pdf
#    https://orka.sejm.gov.pl/Glos9.nsf/nazwa/31_18/$file/GLOS_31_18.PDF
#    https://orka.sejm.gov.pl/Glos9.nsf/nazwa/47_126/$file/Glos_47_126.pdf
#    https://orka.sejm.gov.pl/Glos9.nsf/nazwa/61_141/$file/glos_61_141.pdf
# 3. DATABASE TESTS


# Class for political party
# Stores party's name and a list of all vote stances
class Party:
    def __init__(self, name, vote_stances=None):
        self.name = name

        # Needs to be declared here and not in declaration, because we need a new list every time
        if vote_stances is None:
            self.vote_stances = []

    def __str__(self):
        return self.name


# Class for political party's vote stance on a singular vote
# Contains party's name, vote id and all votes cast by the party members
# Contains function designed to get the number of votes and another to find out party's stance as a whole
class PartyVoteStance:
    def __init__(self, name, vote_id, fors=0, againsts=0, abstains=0, absences=0):
        self.name = name
        self.vote_id = vote_id
        self.fors = fors
        self.againsts = againsts
        self.abstains = abstains
        self.absences = absences

    # Assess party's stance
    def get_vote_stance(self):
        if self.fors == 0 and self.againsts == 0 and self.abstains == 0 and self.absences == 0:
            return "non-existent"
        else:
            if self.fors > self.againsts + self.abstains + self.absences:
                return "for"
            else:
                if self.againsts > self.fors + self.abstains + self.absences:
                    return "against"
                else:
                    if self.abstains > self.fors + self.againsts + self.absences:
                        return "abstain"
                    else:
                        if self.absences > self.fors + self.againsts + self.abstains:
                            return "absence"
                        else:
                            return "none"

    # Get a numer of votes
    def get_n_votes(self):
        return self.fors + self.againsts + self.abstains + self.absences


# Class for a single deputy's vote linking their name, stance and party
class DeputyVote:
    def __init__(self, name, stance, party, n_office_term=0, n_voting_session=0, n_vote_number=0):
        self.name = name
        self.stance = stance
        self.party = party
        self.n_office_term = n_office_term
        self.n_voting_session = n_voting_session
        self.n_vote_number = n_vote_number

# Class for a single vote
# Its object contains all information about a specific vote
class Vote:
    def __init__(self, n_office_term, n_voting_session, n_vote_number, date_time, n_absences, n_votes_for, n_votes_against, n_votes_abstain, description, deputy_votes=None):
        self.n_office_term = n_office_term
        self.n_voting_session = n_voting_session
        self.n_vote_number = n_vote_number
        self.date_time = date_time
        self.n_absences = n_absences
        self.n_votes_for = n_votes_for
        self.n_votes_against = n_votes_against
        self.n_votes_abstain = n_votes_abstain
        self.description = description
        self.deputy_votes = deputy_votes

    # Get the vote's ID
    def get_vote_id(self):
        return str(self.n_office_term) + "_" + str(self.n_voting_session) + "_" + str(self.n_vote_number)


# Class for a single deuputy containing all information about them available
class Deputy:
    def __init__(self, imie_i_nazwisko, party, wybrany_dnia=None, lista=None, okreg=None, liczba_glosow=None, slubowanie=None, funkcja_w_sejmie=None, wygasniecie_mandatu=None, staz_parlamentarny=None, klub_lub_kolo=None, funkcja_w_klubie_lub_kole=None, data_urodzenia=None, miejsce_urodzenia=None, wyksztalcenie=None, tytul_lub_stopien_naukowy=None, ukonczona_szkola=None, zawod=None, email=None):
        self.imie_i_nazwisko = imie_i_nazwisko
        self.party = party
        self.profile_data = {"imie_i_nazwisko": imie_i_nazwisko,
                     "wybrany_dnia": wybrany_dnia,
                     "lista": lista,
                     "okreg": okreg,
                     "liczba_glosow": liczba_glosow,
                     "slubowanie": slubowanie,
                     "funkcja_w_sejmie": funkcja_w_sejmie,
                     "wygasniecie_mandatu": wygasniecie_mandatu,
                     "staz_parlamentarny": staz_parlamentarny,
                     "klub_lub_kolo": klub_lub_kolo,
                     "funkcja_w_klubie_lub_kole": funkcja_w_klubie_lub_kole,
                     "data_urodzenia": data_urodzenia,
                     "miejsce_urodzenia": miejsce_urodzenia,
                     "wyksztalcenie": wyksztalcenie,
                     "tytul_lub_stopien_naukowy": tytul_lub_stopien_naukowy,
                     "ukonczona_szkola": ukonczona_szkola,
                     "zawod": zawod,
                     "email": email}

        self.votes = {}

    def __str__(self):
        return self.imie_i_nazwisko


# Get deputy's info from their profile
def download_deputy_info(n_office_term):
    # Dictionary of regexes used to get corresponding data
    regexes = {"imie_i_nazwisko": r"<div id=\"title_content\"><h1>((?:.|\n)*?)</h1><div id=\"contentBody\">",
            "wybrany_dnia": r"Wybran(?:y|a) dnia:</p><p class=\"right\">((?:.|\n)*?)</p>",
            "lista": r"Lista:</p><p class=\"right\">((?:.|\n)*?)</p>",
            "okreg": r"Okręg wyborczy:</p><p class=\"right\" id=\"okreg\">((?:.|\n)*?)</p>",
            "liczba_glosow": r"Glosy\">Liczba głosów:</p><p class=\"right\">((?:.|\n)*?)</p>",
            "slubowanie": r"Ślubowanie:</p><p class=\"right\">((?:.|\n)*?)</p>",
            "funkcja_w_sejmie": r"Funkcja w Sejmie:</p><p class=\"right\">((?:.|\n)*?)</p>",
            "wygasniecie_mandatu": r"Wygaśnięcie mandatu:</p><p class=\"right\">((?:.|\n)*?)</p>",
            "staz_parlamentarny": r"Staż parlamentarny:</p><p class=\"right\">((?:.|\n)*?)</p>",
            "klub_lub_kolo": r"Klub/koło:</p><p class=\"right\">(?:.* class=\"bold\">)?((?:.|\n)*?)(?:</a>)?</p>",
            "funkcja_w_klubie_lub_kole": r"Funkcja w klubie/kole:</p><p class=\"right\">((?:.|\n)*?)</p>",
            "data_urodzenia": r"Data i miejsce urodzenia:</p><p class=\"right\" id=\"urodzony\">((?:.|\n)*?), .*?</p>",
            "miejsce_urodzenia": r"Data i miejsce urodzenia:</p><p class=\"right\" id=\"urodzony\">.*?, ((?:.|\n)*?)</p>",
            "wyksztalcenie": r"Wykształcenie:</p><p class=\"right\">((?:.|\n)*?)</p>",
            "tytul_lub_stopien_naukowy": r"Tytuł/stopień naukowy:</p><p class=\"right\">((?:.|\n)*?)</p>",
            "ukonczona_szkola": r"Ukończona szkoła:</p><p class=\"right\">((?:.|\n)*?)</p>",
            "zawod": r"Zawód:</p><p class=\"right\">((?:.|\n)*?)</p>",
            "email": r"#(.*?)\">pokaż adres email</a>"
    }

    # Static part of the url
    url_static = "https://www.sejm.gov.pl/Sejm" + str(n_office_term) + ".nsf/posel.xsp?id="

    # Boolean describing whether we've reached the end of the deupty list
    # That list has placeholders to be filled so we need that boolean because accessing ID of nonexisting politician doesn't return 404
    end_of_deputies = False
    deputies = []

    # Loop over possible IDs
    # If we access ID of nonexisting politician, that for loop will be doing nothing thanks to the next while loop
    for i in range(1, 1000):
        while end_of_deputies == False:
            try:
                # Format of dynamic part of the url. 001, 002 etc.
                url_dynamic = str('{0:03}'.format(i))

                # Get the response
                response = get_decoded_response(url_static + url_dynamic)

                # Loop over all keys and values in dictionary of regexes
                for key, value in regexes.items():

                    # Find data matching regexes 
                    matches = re.findall(value, response)

                    # If currently processed data is that politician's full name, create a Deputy class based on it
                    if key == "imie_i_nazwisko":
                        # matches[0] = "" means that we've reached the end of existing deputies, which means our loops end
                        if len(matches) == 1 and matches[0] != "":
                            new_deputy = Deputy(matches[0])
                        else:
                            end_of_deputies = True
                    # If currently processed data is found and isn't empty, add it to the class
                    else:
                        if len(matches) == 1 and matches[0] != "":
                            # Special rule for emails because they are jumbled
                            if key == "email":
                                new_deputy.profile_data[key] = matches[0].replace(" ", "").replace("DOT", ".").replace("AT", "@")
                            else:
                                new_deputy.profile_data[key] = matches[0]

                # Create a list of Deputy objects
                if end_of_deputies == False:
                    deputies.append(new_deputy)

                # If no exception was raised, it means we successfuly scrapped the data so we break out of the current while loop
                # We immediately reach for loop which sends us to the next while loop but with higher iterator
                # This isn't the obvious design choice but by having this while loop we also make sure that we get the data after being ratelimited
                break

            except ConnectionError:
                print("Encountered ConnectionError. Retrying in three minutes.")
                time.sleep(180)
            except TimeoutError:
                print("Encountered TimeoutError. Retrying in three minutes.")
                time.sleep(180)
            except Exception:
                print(traceback.format_exc())

    for deputy in deputies:
        for key, value in deputy.profile_data.items():
            print(key, ": ", value, sep='')
        
        print()


# Get response from the URL and decode its charset and convert special polish characters
def get_decoded_response(url):
    # Persistent loop to get the response, retrying after 3 minutes if we get ratelimited
    # If other exception happens, stop the script since something wrong has happened
    responded = False
    while responded == False:
        try:
            # Get the response
            headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }

            req = urllib.request.Request(url, headers=headers)
            response = urllib.request.urlopen(req)

            # Decode it with response's charset (probably utf-8)
            if response.headers.get_content_charset() is None:
                charset = "utf-8"
            else:
                charset = response.headers.get_content_charset()

            response_decoded = response.read().decode(charset)

            # Convert HTML codes to polish characters
            response_polish = unescape(response_decoded)
            responded = True
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            print(e.reason)
            print("Encountered exception. Retrying in 3 minutes.")
            time.sleep(180)
        except Exception as e:
            print(traceback.format_exc())
            print("Encountered unexpected exception. Stopping.")
            sys.exit()

    return response_polish


# Get vote day URLs
def get_vote_day_urls(n_office_term):
    url = "https://www.sejm.gov.pl/Sejm" + str(n_office_term) + ".nsf/agent.xsp?symbol=posglos&NrKadencji=" + str(n_office_term)
    # Get response
    response = get_decoded_response(url)

    # Search for vote day IDs
    # ID creation is wildly inconsistent so we get them this way
    vote_day_urls = []
    print(response)
    matches = re.findall(r"<TR><TD.*?<A HREF=\"agent.xsp\?symbol=listaglos&IdDnia=(.*?)\"(?:.*?)</TD></TR>", response)
    if len(matches) > 0:
        for match in matches:
            vote_day_urls.append("https://www.sejm.gov.pl/Sejm" + str(n_office_term) + ".nsf/agent.xsp?symbol=listaglos&IdDnia=" + match)

        print(vote_day_urls)
        time.sleep(6000000000)
        return vote_day_urls
    # If no IDs are found, we exit and reevaluate our life choices
    else:
        print(f"Found no vote day urls in {url}. Script cannot continue.")
        sys.exit()


# Get vote URLs from vote day URLs
def get_vote_urls(url, n_office_term):
    # Get response
    response = get_decoded_response(url)

    # Find voting session number and vote number
    matches = re.findall(r"<A HREF=\"agent\.xsp\?symbol=glosowania&NrKadencji=" + str(n_office_term) + "&NrPosiedzenia=(.*?)&NrGlosowania=(.*?)\">", response)
    
    # If we found at least one match
    if len(matches) > 0:
        vote_numbers = []

        # Create vote numbers list
        for match in matches:
            vote_numbers.append(match[1])

        # Remove duplicates, sort naturally
        vote_numbers = natsorted(list(set(vote_numbers)))

        # Create vote URLs from vote numbers
        vote_urls = []
        for vote_number in vote_numbers:
            vote_urls.append("https://www.sejm.gov.pl/Sejm" + str(n_office_term) + ".nsf/agent.xsp?symbol=glosowania&NrKadencji=" + str(n_office_term) + "&NrPosiedzenia=" + matches[0][0] + "&NrGlosowania=" + vote_number)

        return vote_urls

    # If we found no matches, something has gone wrong. Not terribly wrong, just on that day, so we proceed and inform the user.
    else:
        print(f"No vote urls found in {url}. Script continues.")

        return None


# Get URLs of the PDF files on the server from vote URLs
def get_vote_pdf_url(vote_url, n_office_term):
    # Get response
    response = get_decoded_response(vote_url)

    # Find vote number, session number, date and hour
    matches = re.findall(r"<div id=\"title_content\"><h1>Głosowanie nr ([0-9]*) na ([0-9]*)\. posiedzeniu Sejmu<br><small>dnia (.*?) r. o godz. (.*?)</small></h1>", response)

    # If we found a match
    if len(matches) > 0:
        # If we found a proper match
        if len(matches[0]) == 4:
            try:
                # Get date and hour and convert it to how file system on the server wants it
                date_time_string = datetime.datetime.strptime((matches[0][2] + "_" + matches[0][3]), "%d-%m-%Y_%H:%M:%S").strftime("%Y%m%d_%H%M%S")

                # Figure out the long and short urls
                # Most of the files on the server have short URLs but there are some that require long types instead for some reason
                static_url = "https://orka.sejm.gov.pl/Glos" + str(n_office_term) + ".nsf/nazwa/"
                dynamic_url_long_type = static_url + matches[0][1] + "_" + matches[0][0] + "/$file/" + matches[0][1] + "_" + matches[0][0] + "_" + date_time_string + ".pdf"
                dynamic_url_short_type = static_url + matches[0][1] + "_" + matches[0][0] + "/$file/glos_" + matches[0][1] + "_" + matches[0][0] + ".pdf"

                # Return those two urls as a dictionary
                return {"short": dynamic_url_short_type, "long": dynamic_url_long_type}

            # If something couldn't be found, list index exception will be thrown which we catch here
            except IndexError as e:
                print(e.reason)
                print(f"Encountered IndexError in get_vote_pdf_url for {vote_url}")
                print(f"Cannot download file from {vote_url}. It needs to be downloaded manually.")

                return None
            except Exception as e:
                print(traceback.format_exc())
                print(f"Cannot download file from {vote_url}. It needs to be downloaded manually.")

                return None

        # Otherwise script continues but returns None
        else:
            print(f"Found incomplete match in {vote_url}. Script continues.")
            print(f"Cannot download file from {vote_url}. It needs to be downloaded manually.")

            return None

    # Otherwise script continues but returns None
    else:
        print(f"Found no date, hour, vote number or voting session number in {vote_url}. Script continues.")
        print(f"Cannot download file from {vote_url}. It needs to be downloaded manually.")

        return None


# Function for downloading PDF files from URLs
def download_pdf_from_url(url, file_path, overwrite=False):
    # If the file doesn't exist or if it exists but we want to overwrite it, we get the response and save it to a file
    # Print's here are important to inform user what's currently happening since downloading it all takes around an hour
    if not os.path.exists(file_path) or overwrite == True:
        response = urllib.request.urlopen(url)
        file = open(file_path, 'wb')
        file.write(response.read())
        file.close()
        # print("Downloaded", file_path)
    else:
        pass
        # print("File", file_path, "already exists.")


# Main function for downloading voting data
def download_vote_data(n_office_term, overwrite=False, download_range=list(range(1, 5000)), save_path="Download", retry_seconds=180):

    # Get URLs of voting days
    vote_day_urls = get_vote_day_urls(n_office_term)

    # Create path for saved pdfs if it doesn't exist
    if not os.path.exists(save_path):
        try:
            os.mkdir(save_path)
        except Exception as e:
            print("Encountered an exception while creating a download directory. Exiting.")
            print(traceback.format_exc())
            sys.exit()

    # Loop over voting days
    for vote_day_url in vote_day_urls:

        # Get vote URLs from voting days
        vote_urls = get_vote_urls(vote_day_url, n_office_term)

        # If previous function returned us a valid match
        if vote_urls is not None and len(vote_urls) > 0:

            # Loop over vote URLs
            for vote_url in vote_urls:

                # Get current voting session number
                matches = re.findall(r"&NrPosiedzenia=([0-9]*?)&", vote_url)[0]

                # If a proper voting session number was found
                if len(matches) > 0:
                    n_voting_session = matches[0]

                    # If current voting session isn't in list of desired sessions to be downloaded, break current loop
                    if int(n_voting_session) not in download_range:
                        break

                    else:
                        # Loop required in order to bypass connection errors and timeouts
                        downloaded = False
                        while downloaded == False:

                            # Get URLs of pdf files. We get returned a dictionary of two URLs, short and long
                            # Short URL is used in most URLs but there were a couple of voting sessions with long URLs for some reason
                            vote_pdf_url_types = get_vote_pdf_url(vote_url, n_office_term)

                            # If previous function returned a proper match
                            if vote_pdf_url_types is not None:

                                # Set file path and name "(n_office_term)_(n_voting_session)_(n_vote)"
                                file_path = os.path.join(save_path, str(n_office_term) + "_" + vote_pdf_url_types["short"].split("/$file/glos_")[1])

                                # Try downloading short url. If there is no such file on the server, try long url.
                                # If there is no long or short, assume the file has been downloaded for the sake of continuity of the loop
                                # The lack of pdf file also means that something has changed on the database's side of things
                                # If we encounter other connection error, we retry after 3 mins because it's most likely server ratelimiting us
                                # If we encounter any other error, script stops since something else has happened
                                try:
                                    download_pdf_from_url(vote_pdf_url_types["short"], file_path, overwrite)
                                    downloaded = True
                                except (urllib.error.URLError, urllib.error.HTTPError) as e:
                                    if e.reason == "Not Found":
                                        try:
                                            download_pdf_from_url(vote_pdf_url_types["long"], file_path, overwrite)
                                            downloaded = True
                                        except (urllib.error.URLError, urllib.error.HTTPError) as e:
                                            if e.reason == "Not Found":
                                                print("There is no file under those urls", vote_pdf_url_types["long"], vote_pdf_url_types["short"])
                                                downloaded = True
                                            else:
                                                print(e.reason)
                                                print("Encountered exception. Retrying in 3 minutes.")
                                                time.sleep(180)

                                        except Exception as e:
                                            print("Encountered unexpected exception. Stopping.")
                                            print(traceback.format_exc())
                                            sys.exit()
                                    else:
                                        print(e.reason)
                                        print("Encountered exception. Retrying in 3 minutes.")
                                        time.sleep(180)
                                except Exception as e:
                                    print("Encountered unexpected exception. Stopping.")
                                    print(traceback.format_exc())
                                    sys.exit()

                            # If previous function didn't return a proper match, we assume that the file has already been downloaded for the sake of continuity of the loop
                            else:
                                downloaded = True

                # If no proper voting session number was found
                else:
                    print(f"No proper voting session number was found in {vote_url}. Script continues.")


# Function for reading all pdf's of votes and extracting valuable info from them
# I really wish there was some library that would extract text from pdf's without hassle
# PyPDF2 leaves random whitespaces everywhere
# textract seems to be dead
# fitz (pymupdf) has this bug which reads incorrectly names when they are too long because of wrapping (chceck KRZYWONOS-STRYCHARSKA HENRYKA)
# pdftotext's dependencies are too much hassle
# tika, despite the hassle of the need to install java, seems to be the best option, even though it's slow
def read_vote_data(path):
    all_votes = []

    # Get all files in a directory
    files = [f for f in listdir(path) if isfile(join(path, f))]
    #files = files[-10:-1]
    #files = ["9_61_141.pdf", "9_47_126.pdf", "9_31_18.pdf", "9_34_1.pdf"]
    #files = ["9_67_39.pdf"]
    #files = ["9_1_1.pdf"]
    
    # Loop over all files
    # We use natsort here for easier debugging
    for file_name in natsorted(files):

        # If current file is a pdf
        if os.path.splitext(file_name)[-1].lower() == ".pdf":

            # Get path
            file_path = os.path.join(path, file_name)

            # Extract data from pdf to str variable
            raw = parser.from_file(file_path)
            fullText = raw['content']
            #print(fullText)

            # Indicate that an error occured during data extraction
            error = False

            try:
                # Get vote's office term
                match_n_office_term = re.findall(r"(?:Sejm RP (.*?) kadencji|(.*?) (?:k|K)adencja Sejmu RP)", fullText)

                # Remove empty matches from the tuple
                for match in match_n_office_term:
                    match_n_office_term = tuple(filter(None, match))

                # If a match was found
                if len(match_n_office_term) > 0:
                    # Some protocols have arabic numbers, some have roman
                    if match_n_office_term[0].strip().isdigit():
                        n_office_term = match_n_office_term[0].strip()
                    else:
                        n_office_term = roman.fromRoman(match_n_office_term[0].strip())

                # If a match wasn't found, get current term number from the file's name
                # File name's naturally should follow a pattern given by downloading function
                else:
                    try:
                        n_office_term = int(file_name.split("_")[0])
                    except Exception as e:
                        print(traceback.format_exc())
                        print("File name probably doesn't follow an established pattern. Couldn't find the office term. File name: ", file_name)
                        error = True
                
                # Find voting session number, vote number, date of the vote and time of the vote
                try:
                    n_voting_session, n_vote_number, date_time = re.findall(r"(?:POSIEDZENIE|Posiedzenie) ([0-9]+)\.? \- (?:głosowanie|wyniki głosowania) nr ([0-9]+)  ? ?\(([0-9\-/]+ [0-9:]+)\)", fullText)[0]
                except Exception as e:
                    print(traceback.format_exc())
                    print("Couldn't find either a voting session number, vote number, date of the vote or time of the vote. File name: ", file_name)
                    error = True

                # Find number of the votes, votes for, against, abstains, absences, vote title and vote description
                try:
                    n_votes, n_votes_for, n_votes_against, n_votes_abstain, n_absences, description = re.findall(r"GŁOSOWAŁO - ([0-9]+) ZA - ([0-9]+) PRZECIW - ([0-9]+) WSTRZYMAŁO SIĘ - ([0-9]+) NIE GŁOSOWAŁO ?- ([0-9]+)(?: \n|\n)((?:(?: \n|\n)?Większość (?:bezwzględna|ustawowa|bezw. ustawowa|3\/5) -  ?[0-9]+(?: \n|\n)(?: \n|\n))?(?:.|\n)*?)(?: \n|\n)*?.*\([0-9]*\) GŁOSOWAŁO - ", fullText)[0]

                    # Remove whitespaces and newlines from the begining and the end
                    description = description.strip()
                except Exception as e:
                    print(traceback.format_exc())
                    print("Couldn't find either the number of votes, votes for, against, abstains, absences or vote description. File name: ", file_name)
                    error = True

                deputy_votes = []
                parties = []

                # Get party names
                try:
                    matches_parties = re.findall(r"((?:.|\.|\-)*?) ?\n?\(([0-9]+)\) \n?\n?GŁOSOWAŁO - ([0-9]+) ZA - ([0-9]+) PRZECIW - ([0-9]+) WSTRZYM(?:\.|AŁO SIĘ) - ([0-9]+) NIE GŁOS(?:\.|OWAŁO) ?- ([0-9]+)", fullText)
                    for party in matches_parties:
                        parties.append(party[0])

                except Exception as e:
                    print(traceback.format_exc())
                    print("Couldn't find party names. File name: ", file_name)
                    error = True

                # Split full text into parts 
                split_list = re.split(r"(?:.|\.|\-)*? ?\n?\((?:[0-9]+)\) \n?\n?GŁOSOWAŁO - (?:[0-9]+) ZA - (?:[0-9]+) PRZECIW - (?:[0-9]+) WSTRZYM(?:\.|AŁO SIĘ) - (?:[0-9]+) NIE GŁOS(?:\.|OWAŁO) ?- (?:[0-9]+)", fullText)

                # If split was successful and each party has its matching data
                # That +1 is there because in the next step we remove unwanted first split                 
                if len(split_list) > 0 and len(parties) + 1 == len(split_list):
                    # First split contains info already extracted so it is deleted
                    # Here we want only info about particular parties and deputies, which first split doesn't have
                    del split_list[0]

                    # i to iterate over split_list (parties)
                    i = 0

                    # Loop over all parties
                    for party in parties:
                        # Find a deputy and their vote
                        deputies_and_votes = re.findall(r"([A-ZĄĆĘŁŃÓŚŹŻ\- \n]+?) (za|pr\.|ws\.|ng\.) ?", split_list[i])

                        # If we found a match
                        if len(deputies_and_votes) > 0:

                            # Loop over all tuples containing deputies and their votes for currently looped party
                            for deputy_and_vote in deputies_and_votes:
                                # Assign deputies with their respective votes and current parties
                                # Strip is used here because text wrapping sometimes adds some kind of whitespace at the beginning
                                deputy_votes.append(DeputyVote(deputy_and_vote[0].strip().replace("\n", ""), deputy_and_vote[1].strip(), party, n_office_term, n_voting_session, n_vote_number))

                            i = i + 1

                        else:
                            print(traceback.format_exc())
                            print("No deputies found in the split. File name: ", file_name)
                            error = True
                else:
                    print(traceback.format_exc())
                    print("Split list doesn't match parties in file: ", file_name)
                    error = True

                # If no errors were present during extracting process
                if error == False:

                    # Create a vote object with all info extracted from pdf and add it to a list of all votes
                    new_vote = Vote(n_office_term, n_voting_session, n_vote_number, date_time, n_absences, n_votes_for, n_votes_against, n_votes_abstain, description, deputy_votes)
                    all_votes.append(new_vote)

                    #print("Successfully processed ", file_name)

            except Exception as e:
                print("Unexpected exception has occured in file: " + file_name)
                print(traceback.format_exc())

    return all_votes


# Function for putting all extracted info into a database   
def fill_database(cursor, connection, votes, deputyvotes, deputies, parties):
    # Sqlite doesn't have proper error handling with Python, so we have to resort to passes instead of traceback prints in the final stage
    for vote in votes:
        try:
            cursor.execute("INSERT INTO VOTE (N_OFFICE_TERM, N_VOTING_SESSION, N_VOTE, DESCRIPTION, DATE_TIME, N_ABSENCES, N_FORS, N_AGAINSTS, N_ABSTAINS) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (vote.n_office_term, vote.n_voting_session, vote.n_vote_number, vote.description, vote.date_time, vote.n_absences, vote.n_votes_for, vote.n_votes_against, vote.n_votes_abstain))
            connection.commit()
        except Exception as e:
            pass
            #print(traceback.format_exc())

    for deputy in deputies:
        try:
            cursor.execute("INSERT INTO DEPUTY (NAME, PARTY) VALUES (?, ?)", (deputy.imie_i_nazwisko, deputy.party))
            connection.commit()
        except Exception as e:
            pass
            #print(traceback.format_exc())

    for deputyvote in deputyvotes:
        try:
            cursor.execute("SELECT ID FROM DEPUTY WHERE NAME = ? AND PARTY = ?", (deputyvote.name, deputyvote.party))
            deputy_id = int(cursor.fetchone()[0])

            cursor.execute("SELECT ID FROM VOTE WHERE N_OFFICE_TERM = ? AND N_VOTING_SESSION = ? AND N_VOTE = ?", (deputyvote.n_office_term, deputyvote.n_voting_session, deputyvote.n_vote_number))
            vote_id = int(cursor.fetchone()[0])
            
            cursor.execute("INSERT INTO DEPUTYVOTE (VOTE_TYPE, DEPUTY_ID, VOTE_ID) VALUES (?, ?, ?)", (deputyvote.stance, deputy_id, vote_id))
            connection.commit()
        except Exception as e:
            pass
            #print(traceback.format_exc())

    for party in parties:
        try:
            cursor.execute("INSERT INTO PARTY (NAME) VALUES (?)", (party.name,))
            connection.commit()
        except Exception as e:
            pass
            #print(traceback.format_exc())

    cursor.execute("SELECT ID FROM VOTE")
    vote_ids = cursor.fetchall()
    for i in range(len(vote_ids)):
        vote_ids[i] = vote_ids[i][0]

    full_party_stances = np.zeros((len(vote_ids), len(parties)), dtype=PartyVoteStance)

    for vote_n in vote_ids:
        for i, party in enumerate(parties):
            cursor.execute("SELECT VOTE_TYPE FROM DEPUTYVOTE INNER JOIN DEPUTY ON DEPUTYVOTE.DEPUTY_ID = DEPUTY.ID WHERE DEPUTY.PARTY = ? AND DEPUTYVOTE.VOTE_ID = ?", (party.name, vote_n))
            votes_party = cursor.fetchall()

            party_vote_stance = PartyVoteStance(party.name, vote_n, 0, 0, 0, 0)
            for vote_stance in votes_party:
                if vote_stance[0] == "za":
                    party_vote_stance.fors = party_vote_stance.fors + 1
                else:
                    if vote_stance[0] == "pr.":
                        party_vote_stance.againsts = party_vote_stance.againsts + 1
                    else:
                        if vote_stance[0] == "ng.":
                            party_vote_stance.absences = party_vote_stance.absences + 1
                        else:
                            if vote_stance[0] == "ws.":
                                party_vote_stance.abstains = party_vote_stance.abstains + 1
                            else:
                                print("Critical data error")

            full_party_stances[vote_n-1][i] = party_vote_stance

    for vote_n in vote_ids:
        for i in range(len(parties)):
            print(parties[i].name, vote_n, full_party_stances[vote_n-1][i].get_vote_stance(), full_party_stances[vote_n-1][i].name)

    for i in range(len(full_party_stances)):
        for j in range(len(full_party_stances[i])):
            try:
                cursor.execute("SELECT ID FROM PARTY WHERE NAME = ?", (full_party_stances[i][j].name,))
                party_id = cursor.fetchall()[0]
                cursor.execute("INSERT INTO PARTYVOTE (PARTY, PARTY_ID, STANCE, VOTE_ID) VALUES (?, ?, ?, ?)", (full_party_stances[i][j].name, party_id[0], full_party_stances[i][j].get_vote_stance(), full_party_stances[i][j].vote_id))
                connection.commit()
            except Exception as e:
                print(traceback.format_exc())


def stats(cursor, connection):
    cursor.execute("SELECT NAME FROM PARTY")
    party_data = cursor.fetchall()

    parties = []
    for party in party_data:
        parties.append(party[0])

    print(parties)

    cursor.execute("SELECT ID FROM VOTE")
    vote_ids = cursor.fetchall()
    for i in range(len(vote_ids)):
        vote_ids[i] = vote_ids[i][0]

    common_partyvotes = []
    for vote_id in vote_ids:
        cursor.execute("SELECT ID FROM PARTYVOTE WHERE PARTYVOTE.VOTE_ID = ?", (vote_id,))
        temp = cursor.fetchall()
        common_partyvote = []
        for t in temp:
            common_partyvote.append(t[0])

        common_partyvotes.append(common_partyvote)

    party_compatibility_matrix_raw = np.zeros((len(parties), len(parties)), dtype=int)
    party_adversity_matrix_raw = np.zeros((len(parties), len(parties)), dtype=int)
    party_common_matrix_raw = np.zeros((len(parties), len(parties)), dtype=int)

    for common_partyvote in common_partyvotes:
        party_vote_stances = []
        for partyvote_id in common_partyvote:
            cursor.execute("SELECT PARTY, STANCE, VOTE_ID FROM PARTYVOTE WHERE ID = ?", (partyvote_id,))
            name, stance, vote_id = cursor.fetchall()[0]
            party_vote_stance = PartyVoteStance(name, vote_id)
            if stance == "for":
                party_vote_stance.fors = party_vote_stance.fors + 1
            else:
                if stance == "against":
                    party_vote_stance.againsts = party_vote_stance.againsts + 1
                else:
                    if stance == "absence":
                        party_vote_stance.absences = party_vote_stance.absences + 1
                    else:
                        if stance == "abstain":
                            party_vote_stance.abstains = party_vote_stance.abstains + 1
                        else:
                            if stance != "non-existent" and stance != "none":
                                print("Critical data error: ", stance)

            party_vote_stances.append(party_vote_stance)

        for party_vote_stance1 in party_vote_stances:
            if party_vote_stance1.get_vote_stance() != "non-existent":
                for party_vote_stance2 in party_vote_stances:
                    if party_vote_stance2.get_vote_stance() != "non-existent":
                        if party_vote_stance1.get_vote_stance() == party_vote_stance2.get_vote_stance():
                            for i, party1 in enumerate(parties):
                                if party1 == party_vote_stance1.name:
                                    for j, party2 in enumerate(parties):
                                        if party2 == party_vote_stance2.name:
                                            party_compatibility_matrix_raw[i][j] = party_compatibility_matrix_raw[i][j] + 1
                                            party_common_matrix_raw[i][j] = party_common_matrix_raw[i][j] + 1
                        else:
                            for i, party1 in enumerate(parties):
                                if party1 == party_vote_stance1.name:
                                    for j, party2 in enumerate(parties):
                                        if party2 == party_vote_stance2.name:
                                            party_common_matrix_raw[i][j] = party_common_matrix_raw[i][j] + 1

                                            if (party_vote_stance1.get_vote_stance() == "for" and party_vote_stance2.get_vote_stance() == "against") or (party_vote_stance1.get_vote_stance() == "against" and party_vote_stance2.get_vote_stance() == "for"):
                                                party_adversity_matrix_raw[i][j] = party_adversity_matrix_raw[i][j] + 1

    party_compatibility_matrix = np.zeros((len(parties), len(parties)), dtype=float)
    party_adversity_matrix = np.zeros((len(parties), len(parties)), dtype=float)

    for i in range(len(party_compatibility_matrix)):
        for j in range(len(party_compatibility_matrix)):
            if party_common_matrix_raw[i][j] == 0:
                party_compatibility_matrix[i][j] = -10
                party_adversity_matrix[i][j] = -10
                print(parties[i], parties[j], round(party_compatibility_matrix[i][j], 2), round(party_adversity_matrix[i][j], 2))
            else:
                party_compatibility_matrix[i][j] = party_compatibility_matrix_raw[i][j] / party_common_matrix_raw[i][j]
                party_adversity_matrix[i][j] = party_adversity_matrix_raw[i][j] / party_common_matrix_raw[i][j]
                print(parties[i], parties[j], round(party_compatibility_matrix[i][j], 2), round(party_adversity_matrix[i][j], 2))

    cursor.execute("SELECT DEPUTYVOTE.VOTE_ID, DEPUTY.NAME FROM DEPUTYVOTE INNER JOIN DEPUTY ON DEPUTYVOTE.DEPUTY_ID = DEPUTY.ID WHERE DEPUTYVOTE.VOTE_TYPE = ?", ("ng.",))
    deputy_absence_data = cursor.fetchall()
    

    deputy_absences = {}

    for i in deputy_absence_data: 
        deputy_absences[i] = deputy_absence_data.count(i)

    # print(deputy_absences)

    

# Create database and its tables
def create_db(database_path):
    # Create database and its cursor
    connection = sqlite3.connect(os.path.join(database_path, "Database.db"))
    cursor = connection.cursor()

    # Pragma for foreign keys, allows the usage of keys from different tables
    cursor.execute("PRAGMA FOREIGN_KETS = ON")

    # Table of each separate vote
    cursor.execute('''CREATE TABLE IF NOT EXISTS VOTE
        (ID INTEGER PRIMARY KEY,
        N_OFFICE_TERM INTEGER NOT NULL,
        N_VOTING_SESSION INTEGER NOT NULL,
        N_VOTE INTEGER NOT NULL,
        DESCRIPTION TEXT NOT NULL,
        DATE_TIME TEXT NOT NULL,
        N_ABSENCES INTEGER NOT NULL,
        N_FORS INTEGER NOT NULL,
        N_AGAINSTS INTEGER NOT NULL,
        N_ABSTAINS INTEGER NOT NULL,
        UNIQUE (N_OFFICE_TERM, N_VOTING_SESSION, N_VOTE)
        );''')

    # Table of each deputy
    # There can be two or more deputies with same name but different party
    # It's not a bug, it's a feature
    cursor.execute('''CREATE TABLE IF NOT EXISTS DEPUTY(
        ID INTEGER PRIMARY KEY,
        NAME TEXT NOT NULL,
        PARTY TEXT NOT NULL,
        UNIQUE (NAME, PARTY));''')

    # Table linking a deputy, their vote and vote session
    cursor.execute('''CREATE TABLE IF NOT EXISTS DEPUTYVOTE(
        ID INTEGER PRIMARY KEY,
        VOTE_TYPE TEXT NOT NULL,
        DEPUTY_ID INTEGER NOT NULL,
        VOTE_ID INTEGER NOT NULL,
        FOREIGN KEY(DEPUTY_ID) REFERENCES DEPUTY(ID),
        FOREIGN KEY(VOTE_ID) REFERENCES VOTE(ID),
        UNIQUE (DEPUTY_ID, VOTE_ID));''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS PARTYVOTE(
        ID INTEGER PRIMARY KEY,
        PARTY TEXT NOT NULL,
        PARTY_ID INT NOT NULL,
        STANCE TEXT NOT NULL,
        VOTE_ID INTEGER NOT NULL,
        FOREIGN KEY(VOTE_ID) REFERENCES VOTE(ID),
        FOREIGN KEY(PARTY_ID) REFERENCES PARTY(ID),
        UNIQUE (PARTY, VOTE_ID));''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS PARTY(
        ID INTEGER PRIMARY KEY,
        NAME TEXT NOT NULL,
        UNIQUE (NAME));''')

    return cursor, connection


def process_data(all_data):
    votes = []
    deputyvotes = []
    deputies = []
    parties = []

    for i in range(len(all_data)):
        votes.append(all_data[i])

    for i in range(len(votes)):
        for j in range(len(votes[i].deputy_votes)):
            deputyvotes.append(DeputyVote(name=votes[i].deputy_votes[j].name, stance=votes[i].deputy_votes[j].stance, party=votes[i].deputy_votes[j].party, n_office_term=votes[i].n_office_term, n_voting_session=votes[i].n_voting_session, n_vote_number=votes[i].n_vote_number))

    for i in range(len(deputyvotes)):
        duplicate = False
        for j in range(len(deputies)):
            if deputies[j].imie_i_nazwisko == deputyvotes[i].name and deputies[j].party == deputyvotes[i].party:
                duplicate = True
        if duplicate is False:        
            deputies.append(Deputy(imie_i_nazwisko=deputyvotes[i].name, party=deputyvotes[i].party))

    for i in range(len(deputyvotes)):
        duplicate = False
        for j in range(len(parties)):
            if parties[j].name == deputyvotes[i].party:
                duplicate = True
        if duplicate is False:
            parties.append(Party(name=deputyvotes[i].party))

    return votes, deputyvotes, deputies, parties


def main():
    if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "Download")) is False:
        os.mkdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "Download"))

    if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "Database")) is False:
        os.mkdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "Database"))

    # Parse initial arguments
    parser = argparse.ArgumentParser(description="Polish Sejm Vote Downloader and Analyzer")
    parser.add_argument("--download", default=True, help="A boolean defining whether to download all pdfs", type=bool)
    parser.add_argument("--write", default=True, help="A boolean defining whether to write to database", type=bool)
    parser.add_argument("--read", default=True, help="A boolean defining whether to read the database", type=bool)
    parser.add_argument("--n_office_term", default=9, help="Office term number", type=int)
    parser.add_argument("--overwrite_votes", default=False, help="A boolean defining whether downloaded vote pdf's should overwrite existing ones", type=bool)
    parser.add_argument("--download_session_lower", default=1, help="Lower range bound of sessions to be downloaded", type=int)
    parser.add_argument("--download_session_higher", default=5000, help="Higher range bound of sessions to be downloaded", type=int)
    parser.add_argument("--download_path", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "Download"), help="Path to download directory", type=str)
    parser.add_argument("--database_path", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "Database"), help="Path to database directory", type=str)
    args = parser.parse_args()

    if args.download == True:
        # Range of desired voting sessions
        # Defaulting to impossibly large range
        download_range = list(range(args.download_session_lower, args.download_session_higher))

        # Main function for downloading voting data
        download_vote_data(args.n_office_term, overwrite=args.overwrite_votes, download_range=download_range, save_path=args.download_path)

    cursor, connection = create_db(args.database_path)
    if args.write == True:
        all_data = read_vote_data(args.download_path)
        votes, deputyvotes, deputies, parties = process_data(all_data)
        fill_database(cursor, connection, votes, deputyvotes, deputies, parties)

    if args.read == True:
        stats(cursor, connection)


    # 9_8_1 do 9_8_16 w innym trybie

    # IDK

    # 2. https://orka.sejm.gov.pl/Glos9.nsf/nazwa/34_1/$file/glos_34_1.pdf
#    https://orka.sejm.gov.pl/Glos9.nsf/nazwa/31_18/$file/GLOS_31_18.PDF
#    https://orka.sejm.gov.pl/Glos9.nsf/nazwa/47_126/$file/Glos_47_126.pdf
#    https://orka.sejm.gov.pl/Glos9.nsf/nazwa/61_141/$file/glos_61_141.pdf

    #vote_url = "https://www.sejm.gov.pl/Sejm9.nsf/agent.xsp?symbol=glosowania&NrKadencji=9&NrPosiedzenia=59&NrGlosowania=187"
    #print(get_vote_pdf_url(vote_url, 9))




if __name__ == "__main__":
    main()




#### DEPREC

# # Function for putting all extracted info into a database
# def fill_database_deprec(all_votes):
#     # Create database and its tables
#     cursor, connection = create_db()

#     # Loop over all votes
#     for vote in all_votes:
#         try:
#             # Insert every vote into its corresponding table
#             cursor.execute("INSERT INTO VOTE (N_OFFICE_TERM, N_VOTING_SESSION, N_VOTE, DESCRIPTION, DATE_TIME, N_ABSENCES, N_FORS, N_AGAINSTS, N_ABSTAINS) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (vote.n_office_term, vote.n_voting_session, vote.n_vote_number, vote.description, vote.date_time, vote.n_absences, vote.n_votes_for, vote.n_votes_against, vote.n_votes_abstain))
#             connection.commit()

#             # Get the ID of the last insereted vote into a table
#             last_vote_id = int(cursor.lastrowid)

#             # Loop over all deputy votes
#             for deputy_vote in vote.deputy_votes:
#                 try:
#                     # If that deputy isn't in the database already, insert them and get their ID
#                     cursor.execute("INSERT INTO DEPUTY (NAME, PARTY) VALUES (?, ?)", (deputy_vote.name, deputy_vote.party))
#                     connection.commit()
#                     last_deputy_id = int(cursor.lastrowid)
#                 except Exception as e:
#                     # If that deputy is already in the database, find their ID
#                     cursor.execute("SELECT ID FROM DEPUTY WHERE NAME = ? AND PARTY = ?", (deputy_vote.name, deputy_vote.party))
#                     last_deputy_id = int(cursor.fetchone()[0])

#                 try:
#                     # Insert deputy vote into the database, we need both deputy_id and vote_id here to link them
#                     cursor.execute("INSERT INTO DEPUTYVOTE (VOTE_TYPE, DEPUTY_ID, VOTE_ID) VALUES (?, ?, ?)", (deputy_vote.stance, last_deputy_id, last_vote_id))
#                     connection.commit()
#                 except Exception as e:
#                     print("Error while inserting new deputyvote into database.")
#                     print(traceback.format_exc())

#         except Exception as e:
#             print(traceback.format_exc())

#     connection.close()