"""The toolkit: the few things every automation needs, so each example is only its own logic.

    triggers   start an automation: as a job, or as a webhook
    sheets     read a tab, add a row
    ai         one call to a model
    web        follow a link

There are no API keys. On Cloud Run everything signs in as the service account.
"""
from dotenv import load_dotenv

load_dotenv()  # for running an example on your own machine
