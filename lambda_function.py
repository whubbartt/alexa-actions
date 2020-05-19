## VERSION 0.7.1

# UPDATE THESE VARIABLES WITH YOUR CONFIG
HOME_ASSISTANT_URL                = 'https://yourhainstall.com'       # REPLACE WITH THE URL FOR YOUR HA FRONTEND
VERIFY_SSL                        = True                              # SET TO FALSE IF YOU DO NOT HAVE VALID CERTS
TOKEN                             = ''                                # ADD YOUR LONG LIVED TOKEN IF NEEDED OTHERWISE LEAVE BLANK

### NO NEED TO EDIT ANYTHING UNDER THE LINE ###
import logging
import urllib3
import json
import isodate
from datetime import datetime

import ask_sdk_core.utils as ask_utils
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler
from ask_sdk_core.dispatch_components import AbstractExceptionHandler
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_model.slu.entityresolution import StatusCode
from ask_sdk_model import Response

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


INPUT_TEXT_ENTITY = "input_text.alexa_actionable_notification"

RESPONSE_YES = "ResponseYes"
RESPONSE_NO = "ResponseNo"
RESPONSE_NONE = "ResponseNone"
RESPONSE_SELECT = "ResponseSelect"
RESPONSE_NUMERIC = "ResponseNumeric"
RESPONSE_DURATION = "ResponseDuration"


class Borg:
    """Borg MonoState Class for State Persistence."""
    _shared_state = {}
    def __init__(self):
        self.__dict__ = self._shared_state

class HomeAssistant(Borg):
    """HomeAssistant Wrapper Class."""
    def __init__(self, handler_input=None):
        Borg.__init__(self)
        if handler_input: 
            self.handler_input = handler_input

        self.token = self._fetch_token() if TOKEN == "" else TOKEN
        
        if not hasattr(self, 'ha_state') or self.ha_state is None:
            self.get_ha_state()
    
    def _clear_state(self):
        self.ha_state = None

    def _fetch_token(self):
        return ask_utils.get_account_linking_access_token(self.handler_input)

    def _check_response_errors(self, response):
        if response.status == 401:
            print("401 Error", response.data) ## Add proper logging
            return "It looks like I am unauthorized to reach home assistant, \
                    please check your account linking or your long lived access \
                    token and try again."
        elif response.status == 404:
            print("404 Error", response.data) ## Add proper logging
            return "It looks like I may not be able to find the input text entity. \
                    Please check that you've added it to home assistant and try again"
        elif response.status >= 400:
            print(f"{response.status} Error", response.data) ## Add proper logging
            return "Could not communicate with home assistant. Please check the Amazon \
                    CloudWatch logs in the custom skill developer console."

        return None

    def get_ha_state(self):
        """Get State from HA."""
        
        http = urllib3.PoolManager(
            cert_reqs='CERT_REQUIRED' if VERIFY_SSL else 'CERT_NONE',
            timeout=urllib3.Timeout(connect=10.0, read=10.0)
        )

        response = http.request(
            'GET', 
            '{}/api/states/{}'.format(HOME_ASSISTANT_URL, INPUT_TEXT_ENTITY),
            headers={
                'Authorization': 'Bearer {}'.format(self.token),
                'Content-Type': 'application/json'
            },
        )

        errors = self._check_response_errors(response)
        if not errors:
            self.ha_state = {
                "error": True,
                "text": errors
            }

        decoded_response = json.loads(response.data.decode('utf-8'))['state']
        
        self.ha_state = {
            "error": False,
            "event_id": json.loads(decoded_response)['event'],
            "text": json.loads(decoded_response)['text']
        }
        
    def post_ha_event(self, response: str, response_type: str, **kwargs):
        """Send event to HA."""
        
        http = urllib3.PoolManager(
            cert_reqs='CERT_REQUIRED' if VERIFY_SSL else 'CERT_NONE',
            timeout=urllib3.Timeout(connect=10.0, read=10.0)
        )

        request_body = {
            "event_id": self.ha_state['event_id'],
            "event_response": response,
            "event_response_type": response_type
        }
        request_body.update(kwargs)
        
        if self.handler_input.request_envelope.context.system.person:
            person_id = self.handler_input.request_envelope.context.system.person.person_id
            request_body['event_person_id'] = person_id
            
        response = http.request(
            'POST', 
            '{}/api/events/alexa_actionable_notification'.format(HOME_ASSISTANT_URL),
            headers={
                'Authorization': 'Bearer {}'.format(self.token),
                'Content-Type': 'application/json'
            },
            body=json.dumps(request_body).encode('utf-8')
        )
        
        error = self._check_response_errors(response)

        if error:
            return error
        
        self._clear_state()
        return "Okay"

    def get_value_for_slot(self, slot_name):
        """"Get value from slot, also know as the (why does amazon make you do this)"""
        slot = ask_utils.get_slot(self.handler_input, slot_name=slot_name)
        if slot and slot.resolutions and slot.resolutions.resolutions_per_authority:
            for resolution in slot.resolutions.resolutions_per_authority:
                if resolution.status.code == StatusCode.ER_SUCCESS_MATCH:
                    for value in resolution.values:
                        if value.value and value.value.name:
                            return value.value.name


class LaunchRequestHandler(AbstractRequestHandler):
    """Handler for Skill Launch."""
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        home_assistant_object = HomeAssistant(handler_input)
        speak_output = home_assistant_object.ha_state['text'] 

        return (
            handler_input.response_builder
                .speak(speak_output)
                .ask('')
                .response
        )


class YesIntentHanlder(AbstractRequestHandler):
    """Handler for Yes Intent."""
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.YesIntent")(handler_input)

    def handle(self, handler_input):
        home_assistant_object = HomeAssistant(handler_input)
        speak_output = home_assistant_object.post_ha_event(RESPONSE_YES, RESPONSE_YES)

        return (
            handler_input.response_builder
                .speak(speak_output)
                .response
        )


class NoIntentHanlder(AbstractRequestHandler):
    """Handler for No Intent."""
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.NoIntent")(handler_input)

    def handle(self, handler_input):
        home_assistant_object = HomeAssistant(handler_input)
        speak_output = home_assistant_object.post_ha_event(RESPONSE_NO, RESPONSE_NO)   

        return (
            handler_input.response_builder
                .speak(speak_output)
                .response
        )


class NumericIntentHandler(AbstractRequestHandler):
    """Handler for Select Intent."""
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("Number")(handler_input)

    def handle(self, handler_input):
        home_assistant_object = HomeAssistant(handler_input)
        number  = ask_utils.get_slot_value(handler_input, "Numbers")
        if number == '?':
            raise
        speak_output = home_assistant_object.post_ha_event(number, RESPONSE_NUMERIC)

        return (
            handler_input.response_builder
                .speak(speak_output)
                .response
        )


class SelectIntentHandler(AbstractRequestHandler):
    """Handler for Select Intent."""
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("Select")(handler_input)

    def handle(self, handler_input):
        home_assistant_object = HomeAssistant(handler_input)
        selection  = home_assistant_object.get_value_for_slot("Selections")
        if selection:
            home_assistant_object.post_ha_event(selection, RESPONSE_SELECT)
            speak_output = "You selected " + selection
        else:
            raise

        return (
            handler_input.response_builder
                .speak(speak_output)
                .response
        )


class DurationIntentHandler(AbstractRequestHandler):
    """Handler for Select Intent."""
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("Duration")(handler_input)

    def handle(self, handler_input):
        home_assistant_object = HomeAssistant(handler_input)
        duration  = ask_utils.get_slot_value(handler_input, "Durations")
        speak_output = home_assistant_object.post_ha_event(isodate.parse_duration(duration).total_seconds(), RESPONSE_DURATION)

        return (
            handler_input.response_builder
                .speak(speak_output)
                .response
        )


class DateTimeIntentHandler(AbstractRequestHandler):
    """Handler for Select Intent."""
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("Date")(handler_input)

    def handle(self, handler_input):
        home_assistant_object = HomeAssistant(handler_input)
        
        dates = ask_utils.get_slot_value(handler_input, "Dates")
        times = ask_utils.get_slot_value(handler_input, "Times")
        
        if not dates and not times:
            raise
        
        speak_output = "Sorry, I can not do specific dates right now, try a duration instead, like... in 5 hours"

        return (
            handler_input.response_builder
                .speak(speak_output)
                .ask('')
                .response
        )


class CancelOrStopIntentHandler(AbstractRequestHandler):
    """Single handler for Cancel and Stop Intent."""
    def can_handle(self, handler_input):
        return (ask_utils.is_intent_name("AMAZON.CancelIntent")(handler_input) or
                ask_utils.is_intent_name("AMAZON.StopIntent")(handler_input))

    def handle(self, handler_input):
        print("CancelOrStopIntentHandler")
        speak_output = "Goodbye!"

        return (
            handler_input.response_builder
                .speak(speak_output)
                .response
        )


class SessionEndedRequestHandler(AbstractRequestHandler):
    """Handler for Session End."""
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        home_assistant_object = HomeAssistant()
        speak_output = home_assistant_object.post_ha_event(RESPONSE_NONE, RESPONSE_NONE)

        return handler_input.response_builder.response


class IntentReflectorHandler(AbstractRequestHandler):
    """The intent reflector is used for interaction model testing and debugging.
    It will simply repeat the intent the user said. You can create custom handlers
    for your intents by defining them above, then also adding them to the request
    handler chain below.
    """
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("IntentRequest")(handler_input)

    def handle(self, handler_input):
        intent_name = ask_utils.get_intent_name(handler_input)
        speak_output = "You just triggered " + intent_name + "."

        return (
            handler_input.response_builder
                .speak(speak_output)
                .response
        )


class CatchAllExceptionHandler(AbstractExceptionHandler):
    """Generic error handling to capture any syntax or routing errors. If you receive an error
    stating the request handler chain is not found, you have not implemented a handler for
    the intent being invoked or included it in the skill builder below.
    """
    def can_handle(self, handler_input, exception):
        return True

    def handle(self, handler_input, exception):
        print("CatchAllExceptionHandler")
        logger.error(exception, exc_info=True)
        speak_output = "Sorry, I had trouble doing what you asked, or couldn't understand you. \
                        Please try again."

        return (
            handler_input.response_builder
                .speak(speak_output)
                .ask('')
                .response
        )

# The SkillBuilder object acts as the entry point for your skill, routing all request and response
# payloads to the handlers above. Make sure any new handlers or interceptors you've
# defined are included below. The order matters - they're processed top to bottom.

sb = SkillBuilder()

sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(YesIntentHanlder())
sb.add_request_handler(NoIntentHanlder())
sb.add_request_handler(SelectIntentHandler())
sb.add_request_handler(NumericIntentHandler())
sb.add_request_handler(DurationIntentHandler())
sb.add_request_handler(DateTimeIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())

sb.add_request_handler(IntentReflectorHandler()) 
sb.add_exception_handler(CatchAllExceptionHandler())

lambda_handler = sb.lambda_handler()
