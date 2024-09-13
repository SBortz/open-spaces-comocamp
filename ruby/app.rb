require 'sinatra'
require "sinatra/reloader" if development?
require 'json'
require 'fileutils'
require 'ostruct'
require 'logger'
require 'rqrcode'

configure do
  set :bind, '0.0.0.0'
end

require_relative 'commands/close_registration_cd'
require_relative 'commands/open_registration_cmd'

require_relative 'events/unique_id_provided_event'
require_relative 'events/registration_opened_event'
require_relative 'events/registration_closed_event'

log = Logger.new(STDOUT)

EVENT_STORE_PATH = File.expand_path(File.join(__dir__, '..', 'eventstore'))

def write_event_if_id_not_exists(event)
  Dir.mkdir(EVENT_STORE_PATH) unless Dir.exist?(EVENT_STORE_PATH)
  event_files = Dir.entries(EVENT_STORE_PATH).select { |file| file.include?(event.id) }
  if event_files.empty? then timestamp = event.timestamp.gsub(':', '-').gsub(/\..+/, '')
    file_name = "#{timestamp}-#{event.id}-#{event.type}.json"
    File.write(File.join(EVENT_STORE_PATH, file_name), JSON.generate(event.to_h))
  end
end

# glossary:
# sv / rm = State View / Read Model
# cd / cmd = Command

def get_all_events
  Dir.mkdir(EVENT_STORE_PATH) unless Dir.exist?(EVENT_STORE_PATH)
  Dir.entries(EVENT_STORE_PATH).select { |file| file.end_with?('.json') }.map { |file| OpenStruct.new(JSON.parse(File.read(File.join(EVENT_STORE_PATH, file)))) }
end

get "/show_registration_qr_code/:uuid" do
  logger.info ">> GET /show_registration_qr_code, params[:uuid]: #{params[:uuid]}"
  result = handle_show_registration_qr_code_cmd(get_all_events, OpenRegistrationCmd.new(params[:uuid], Time.now.utc.iso8601, SecureRandom.uuid))
  halt 400, result[:error] unless result[:error].empty?
  erb :show_registration_qr_code, locals: { conf_id: params[:uuid] }
end

def handle_show_registration_qr_code_cmd(events, command)
  # check for an RegistrationOpened event of the requested conference;
  # only show the QR code if it exists
  logger.info "events: #{events}"
  last_event = events.select { |event| event.id == command.confId }
  .select { |event| ['RegistrationOpenedEvent', 'RegistrationClosedEvent'].include?(event.type) }
  .sort_by { |event| event.timestamp }
  .last
  registration_open = last_event&.type == 'RegistrationOpenedEvent'

  logger.info "last_event: #{last_event}"

  if registration_open
    logger.info "YEAH"
    # erb :show_registration_qr_code
    return { error: [], events: [] }
  else
      return { error: "Registration for conference with id #{command.confId} is currently not open", events: [] }
  end
end

get "/register_for_conference/:uuid" do
  # check for an RegistrationOpened event of the requested conference
  events = registration_status_sv(get_all_events)

  erb :register_for_conference, locals: { supplied_uuid: params[:uuid], conference_id: conference_ids_sv(get_all_events).last, registration_status: registration_status_sv(get_all_events) }
end

get "/portal_management" do erb :portal_management, locals: { conference_id: conference_ids_sv(get_all_events).last, registration_status: registration_status_sv(get_all_events) } end

def conference_ids_sv(events_array)
  events_array.select { |event| event.type == 'UniqueIdProvidedEvent' }.sort_by { |event| event.timestamp }.reverse.map { |event| { conf_id: event.confId, qr: event.qr, url: event.url } }
end

def registration_status_sv(events_array)
  conf_id = (unique_id_event = events_array.reverse.find { |event| event.type == 'UniqueIdProvidedEvent' }) ? unique_id_event.confId : nil
  return { conf_id: '', status: '', error_message: 'No unique ID provided' } if conf_id.nil?

  registration_opened = events_array.any? { |event| event.type == 'RegistrationOpenedEvent' && event.confId == conf_id }
  registration_closed = events_array.any? { |event| event.type == 'RegistrationClosedEvent' && event.confId == conf_id }
  status = registration_closed ? 'closed' : (registration_opened ? 'open' : 'closed')

  { conf_id: conf_id, status: status, error_message: '' }
end

post "/close_registration" do
  result = handle_close_registration_cd(get_all_events, CloseRegistrationCD.new(params[:confId], Time.now.utc.iso8601, SecureRandom.uuid))
  halt 400, result[:error] unless result[:error].empty?

  begin
    result[:events].each { |event| write_event_if_id_not_exists(event) }
    redirect '/portal_management'
  rescue => e
    status 500
    body "Failed to write event to the file system: #{e.message}"
  end
end

def handle_close_registration_cd(events_array, command)
  last_event = events_array.select { |event| event.confId == command.confId }
    .select { |event| ['RegistrationOpenedEvent', 'RegistrationClosedEvent'].include?(event.type) }
    .sort_by { |event| event.timestamp }
    .last

  registration_closed = last_event.type == 'RegistrationClosedEvent'
  if registration_closed
    return { error: "Registration already closed", events: [] }
  end

  { error: "", events: [RegistrationClosedEvent.new(command.confId, command.timestamp, command.id)] }
end
