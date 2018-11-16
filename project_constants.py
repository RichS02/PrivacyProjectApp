from pathlib import Path
# Configurable Constants
VERSION_NUM = 2
STUDY_DURATION = 4  # 4 weeks
SLEEP_TIME = 12  # Sleep for 12 hours (using datetime) after processing CAP articles.
CAP = 500  # Limit number of articles to process to 500 in one processing session.
RECORD_TIME_LIMIT = 31540000  # Don't fetch any links > year (seconds) in history.
HOME_PATH = str(Path.home())+"/com.stony-brook.nlp.privacy-project"
GOOGLE_FORM_FILL_PATH = "https://docs.google.com/forms/d/e/1FAIpQLSfNF-x2fsf0BTpqlrlHxrHxRRjxgxTV4vdsewgENxzJuYBhsA/viewform?usp=pp_url&entry.1537839056="