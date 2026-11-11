"""The toolkit: the few things every automation needs, so each example is only its own logic.

    triggers   start an automation: as a job, or as a webhook
    sheets     read a tab, add a row
    drive      find new files in a folder, download one, mark it as done
    ai         one call to a model, or an agent with tools
    web        follow a link, tell the team

There are no API keys. On Cloud Run everything signs in as the service account.
"""
import logging

from dotenv import load_dotenv

load_dotenv()  # for running an example on your own machine
logging.getLogger("google_auth_httplib2").setLevel(logging.ERROR)  # it warns about timeouts on every Google call
