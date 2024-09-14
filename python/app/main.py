import uuid
from datetime import datetime

import uvicorn
from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from starlette import status
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastapi.responses import RedirectResponse

from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from commands.add_room import AddRoomCD
from commands.add_time_slot import AddTimeSlotCD
from events.base import Event
from commands.CommandsHandler import CommandsHandler
from events_store.events_store import EventStore

from read_models.hosted_conferences import HostedConferencesList

app = FastAPI(docs_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory='./static'), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.get("/events")
def get_events():
    """
    Endpoint to test event store retrieval of all events from this slice
    :return:
    """
    return EventStore.get_all_events()


@app.post("/event")
def post_event(event: Event):
    """
    Endpoint to test event store writing of events from this slice

    :param event:
    :return:
    """
    event_id = EventStore.write_event_if_id_not_exists(event)
    return {
        'message': f'Event written with id {event_id}'
    }


# state view for rooms and time slots
def rooms_and_time_slots_view(conference_id: str):
    events_list: list = EventStore.get_all_events()
    result = {}
    for event in events_list:
        if event.get('type') == 'ConferenceClaimedEvent' and event.get('conferenceId') == conference_id:
            result['conferenceName'] = event.get('name')
            result['conferenceId'] = event.get('conferenceId')
            break
    for event in events_list:
        if event.get('type') == 'RoomAdded' and event.get('conferenceId') == conference_id:
            if 'rooms' not in result:
                result['rooms'] = []
            result['rooms'].append(
                {
                    'room': event.get('room'),
                    'capacity': event.get('capacity')
                }
            )
    for event in events_list:
        if event.get('type') == 'TimeSlotAdded' and event.get('conferenceId') == conference_id:
            if 'timeSlots' not in result:
                result['timeSlots'] = []
            result['timeSlots'].append(
                {
                    'startTime': event.get('startTime'),
                    'endTime': event.get('endTime')
                }
            )
    return result


# state view for payment
@app.get('/rooms_and_time_slots')
def get_cart(request: Request, conference_id: str):
    """
    Endpoint to view checkout page

    :return:
    """
    events = rooms_and_time_slots_view(conference_id)

    if not events:
        return templates.TemplateResponse(
            request=request, name="conference_not_found.jinja2", context={
                "data": events
            }
        )
    else:
        return templates.TemplateResponse(
            request=request, name="rooms_and_time_slots.jinja2", context={
                "data": events
            }
        )


@app.get("/add_rooms")
async def add_rooms(request: Request):
    """
    Endpoint to add a room

    :param request:
    :return:
    """
    events = EventStore.get_all_events()
    conference_name = None
    conference_id = None

    # sort by timestamp and get latest
    events = sorted(events, key=lambda x: x.get('timestamp'), reverse=True)
    for event in events:
        if event.get('type') == 'ConferenceClaimedEvent':
            conference_name = event.get('name')
            conference_id = event.get('conferenceId')
            break
    return templates.TemplateResponse(
        request=request, name="add_room.jinja2", context={
            "data": {
                "conference_id": conference_id,
                "conference_name": conference_name
            },
        }
    )


# command handler for adding a room
@app.post("/add_room")
async def add_room(request: Request):
    """

    :param request:
    :return:
    """
    payload = await request.json()
    print(payload)
    handler = CommandsHandler()
    event_id: str = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()

    command = AddRoomCD(
        **{
            'conferenceId': payload.get('conferenceId'),
            'room': payload.get('roomName'),
            'capacity': payload.get('capacity')
        }
    )
    handler.add_room_command(event_id, timestamp, command)
    # redirect to rooms_and_time_slots view
    return RedirectResponse(
        url=f'rooms_and_time_slots?conference_id={command.conferenceId}',
        status_code=status.HTTP_302_FOUND
    )


@app.post("/open_registration")
def open_registration(conference_id: str):
    """
    Command handler for open registration

    :param conference_id:

    :return:
    """
    event_id: str = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()
    handler = CommandsHandler()
    handler.open_registration_command(event_id, timestamp, conference_id)
    return {
        'message': f'Registration opened for conference {conference_id}'
    }



# Time Slots
@app.get("/add_time_slots")
async def add_rooms(request: Request):
    """
    Endpoint to add a room

    :param request:
    :return:
    """
    events = EventStore.get_all_events()
    conference_name = None
    conference_id = None
    events = sorted(events, key=lambda x: x.get('timestamp'), reverse=True)
    for event in events:
        if event.get('type') == 'ConferenceClaimedEvent':
            conference_name = event.get('name')
            conference_id = event.get('conferenceId')
            break
    return templates.TemplateResponse(
        request=request, name="add_time_slot.jinja2", context={
            "data": {
                "conference_id": conference_id,
                "conference_name": conference_name
            },
        }
    )


@app.post("/add_time_slot")
async def add_time_slot(request: Request):
    """

    :param request:
    :return:
    """
    payload = await request.json()
    print(payload)
    handler = CommandsHandler()
    event_id: str = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()

    command = AddTimeSlotCD(
        **{
            'conferenceId': payload.get('conferenceId'),
            'startTime': payload.get('startTime'),
            'endTime': payload.get('endTime')
        }
    )
    handler.add_time_slot_command(event_id, timestamp, command)
    # redirect to rooms_and_time_slots view
    return RedirectResponse(
        url=f'rooms_and_time_slots?conference_id={command.conferenceId}',
        status_code=status.HTTP_302_FOUND
    )


@app.get('/rooms_and_time_slots_assignment')
def get_cart(request: Request, conference_id: str):
    """
    Endpoint to view checkout page

    :return:
    """
    events = rooms_and_time_slots_view(conference_id)

    if not events:
        return templates.TemplateResponse(
            request=request, name="conference_not_found.jinja2", context={
                "data": events
            }
        )
    else:
        return templates.TemplateResponse(
            request=request, name="rooms_and_time_slots_assignment.jinja2", context={
                "data": events
            }
        )


@app.get('/assign_topic')
async def assign_topic(request: Request):
    """
    Endpoint to assign topic

    :param request:
    :return:
    """
    room = request.query_params.get('room')
    time_slot = request.query_params.get('time_slot')
    return templates.TemplateResponse(
        request=request, name="assign_topic.jinja2", context={
            "data": {
                "room": room,
                "time_slot": time_slot,
            },
        }
    )


@app.get("/openapi.json", include_in_schema=False)
async def get_open_api_endpoint():
    return JSONResponse(get_openapi(
        title='python-slice',
        version='0.0.1',
        routes=app.routes
    ))


@app.get("/docs", include_in_schema=False)
async def get_documentation(request: Request):
    return get_swagger_ui_html(openapi_url="openapi.json", title="docs")


uvicorn.run(app, host="0.0.0.0", port=5656)
