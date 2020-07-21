#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Touch Portal [tpHandler] © Autolog & DaveL17 2020
#

# noinspection PyUnresolvedReferences
# ============================== Native Imports ===============================
import json
import logging
import Queue
import re
import socket
import sys
import threading

# ============================== Custom Imports ===============================
try:
    import indigo
except ImportError:
    pass

# ============================== Plugin Imports ===============================
from constants import *


# noinspection PyUnresolvedReferences,PyPep8Naming,PyPep8
class ThreadTpHandler(threading.Thread):

    # This class handles Touch Portal processing

    def __init__(self, pluginGlobals, event, touchPortalDeviceId):

        threading.Thread.__init__(self)

        self.globals = pluginGlobals
        self.dev_id = touchPortalDeviceId
        self.tph_logger = logging.getLogger("Plugin.TP_HANDLER")
        self.tph_logger.debug(u"Debugging Touch Portal Handler Thread")
        self.thread_stop = event

    # =============================================================================
    def handle_communication(self, dev):
        """
        Read Queue messages and process accordingly

        -----
        :param dev:
        :return:
        """
        try:
            dev_id = dev.id
            socket_error_message = ""

            while not self.thread_stop.is_set() and socket_error_message == "":
                # noinspection PyPep8,PyBroadException
                try:
                    tp_queued_entry = self.globals[K_QUEUES][self.dev_id][K_RECEIVE_FROM_SEND_TO_TP].get(True, 3)  # blockings

                    # tpQueuedEntry format:
                    #   - Priority
                    #   - Command
                    #   - Device
                    #   - Data

                    self.tph_logger.debug(u"DEQUEUED MESSAGE = {0}".format(tp_queued_entry))
                    tp_queue_priority, tp_queue_sequence, tp_command, tp_command_dev_id, tp_command_package = tp_queued_entry

                    if tp_command_dev_id is not None:
                        self.tph_logger.debug(u"\nTPHANDLER: '{0}' DEQUEUED COMMAND '{1}'".format(indigo.devices[tp_command_dev_id].name, CMD_TRANSLATION[tp_command]))
                    else:
                        self.tph_logger.debug(u"\nTPHANDLER: DEQUEUED COMMAND '{0}'".format(CMD_TRANSLATION[tp_command]))

                    if tp_command == CMD_PROCESS_SEND_TP_MESSAGE:
                        message_to_send = tp_command_package[0]
                        self.process_send_tp_message(tp_command_dev_id, message_to_send)  # Process message to send to Touch Portal Desktop App
                        continue
                    elif tp_command == CMD_PROCESS_RECEIVED_TP_MESSAGE:
                        message_received = tp_command_package[0]
                        self.process_receive_tp_message(dev, message_received)  # Process message received from Touch Portal Desktop App
                        continue
                    elif tp_command == CMD_PROCESS_REFRESH_TP_PLUGIN_STATES:
                        self.process_refresh_tp_states(dev_id)  # Process Refresh TP Plugin States
                        continue
                    else:
                        try:
                            # Processing for known command not yet added to tpHandler - info message only
                            self.tph_logger.info(u"TPHandler: '{0}' command cannot be processed - ignored".format(CMD_TRANSLATION[tp_command]))
                        except StandardError:
                            # Handle situation where command is completely unknown and no translation exists = error!
                            self.tph_logger.error(u"TPHandler: '{0}' unknown command cannot be processed".format(tp_command))

                except Queue.Empty:
                    pass
                except StandardError as standard_error_message:
                    self.tph_logger.error(u"StandardError detected in TP Handler Thread. Line '{0}' has error='{1}'".format(sys.exc_traceback.tb_lineno, standard_error_message))
                    socket_error_message = u"See Indigo Error Log"
                except Exception:  # Catch any other error
                    self.tph_logger.error(u"Unexpected Exception detected in TP Handler Thread. Line '{0}' has error='{1}'".format(
                        sys.exc_traceback.tb_lineno, sys.exc_info()[0]))
                    socket_error_message = u"See Indigo Error Log"

        except StandardError as standard_error_message:
            self.tph_logger.error(u"StandardError detected in TP Handler Thread - handleCommunication . Line '{0}' has error='{1}'".format(sys.exc_traceback.tb_lineno,
                                                                                                                                           standard_error_message))

        # End of While loop and TP Handler thread will close down

    # =============================================================================
    def process_receive_tp_message(self, dev, dataReceived):
        """
        Process message received from Touch Portal Desktop.
        Process as appropriate: Indigo device/action group/variable command

        -----
        :param dev:
        :param dataReceived:
        :return:
        """
        try:

            self.tph_logger.debug(u"processReceiveTpMessage: {0}".format(dataReceived))

            try:
                converted_data = json.loads(dataReceived)
                self.tph_logger.debug(u"Received [Converted Data]: '{0}'".format(converted_data))
            except ValueError:
                self.tph_logger.debug(u"Received [JSON Data] could not be decoded: '{0}'".format(dataReceived))
                return  # Invalid

            tp_type = converted_data["type"]

            self.tph_logger.debug("Type '{0}' received from Touch Portal Desktop".format(tp_type))

            if tp_type == "action":
                self.process_receive_tp_message_action(dev, converted_data)
            elif tp_type == "info":
                self.process_receive_tp_message_info(dev, converted_data)
            elif tp_type == "listChange":
                self.process_receive_tp_message_list_change(dev, converted_data)
            elif tp_type == "closePlugin":
                self.tph_logger.warning("Type '{0}' received from Touch Portal Desktop".format(tp_type))

            # Unknown tp_type, so ignore.

        except StandardError as standard_error_message:
            self.tph_logger.error(u"StandardError detected in 'processReceiveTpMessage'. Line '{0}' has error='{1}'".format(sys.exc_traceback.tb_lineno, standard_error_message))

    # =============================================================================
    def process_receive_tp_message_action(self, dev, converted_data):
        """
        Process message received from Touch Portal Desktop.
        Process as appropriate: Indigo device/action group/variable command

        -----
        :param dev:
        :param converted_data:
        :return:
        """
        try:
            dev_id = dev.id

            # tp_pluginId = converted_data['pluginId']  # Reserved for future use

            tp_device_name = None
            tp_brightness_value = None
            tp_brighten_value = None
            tp_dim_value = None
            tp_colour_value = None
            tp_action_group_name = None
            tp_variable_name = None
            tp_variable_value = None

            for data_entry in converted_data["data"]:
                if data_entry["id"] == "indigo_device_name_on_off":
                    if "value" in data_entry:
                        tp_device_name = data_entry["value"]
                elif data_entry["id"] == "indigo_device_name_brightness":
                    if "value" in data_entry:
                        tp_device_name = data_entry["value"]
                elif data_entry["id"] == "indigo_device_name_rgb":
                    if "value" in data_entry:
                        tp_device_name = data_entry["value"]
                elif data_entry["id"] == "indigo_device_brightness_value":
                    if "value" in data_entry:
                        tp_brightness_value = data_entry["value"]
                elif data_entry["id"] == "indigo_device_brighten_value":
                    if "value" in data_entry:
                        tp_brighten_value = data_entry["value"]
                elif data_entry["id"] == "indigo_device_dim_value":
                    if "value" in data_entry:
                        tp_dim_value = data_entry["value"]
                elif data_entry["id"] == "indigo_device_colour_value":
                    if "value" in data_entry:
                        tp_colour_value = data_entry["value"]
                elif data_entry["id"] == "indigo_action_group_name":
                    if "value" in data_entry:
                        tp_action_group_name = data_entry["value"]
                elif data_entry["id"] == "indigo_variable_name_text":
                    if "value" in data_entry:
                        tp_variable_name = data_entry["value"]
                elif data_entry["id"] == "indigo_variable_name_true_false":
                    if "value" in data_entry:
                        tp_variable_name = data_entry["value"]
                elif data_entry["id"] == "indigo_variable_value":
                    if "value" in data_entry:
                        tp_variable_value = data_entry["value"]

            debug_show_messages_from_tp_desktop = self.globals[K_DEBUG][K_SHOW_MESSAGES]

            # Retrieve known TP Devices from Indigo Touch Portal Device
            tp_devices_pre_json = indigo.devices[dev_id].pluginProps.get("tp_devices", None)
            self.tph_logger.debug(u"TP DEVICES:\n{0}\n".format(tp_devices_pre_json))

            if tp_devices_pre_json is None:
                self.tph_logger.warning(u"TP DEVICES MISSING")  # TODO: Needs Enhancing
                return
            tp_devices = json.loads(tp_devices_pre_json)

            tp_action = converted_data["actionId"]

            if "device_" in tp_action and tp_action in TP_ENTRY_COMMANDS_DEVICE:
                if tp_device_name is None or tp_device_name == "":
                    self.tph_logger.error(
                        "Action '{0}' received from Touch Portal Desktop App with missing Touch Portal Device name".format(TP_ENTRY_TRANSLATION[tp_action]))
                    return  # Invalid

                # validate request and determine related Indigo Device
                valid = True  # Assume valid request
                indigo_device_id = 0  # Only needed to suppress PyCharm 'referenced before assignment' warning
                tp_device_name_key = tp_device_name.lower()  # Key is lowercase
                if tp_device_name_key not in tp_devices:
                    valid = False  # TP Device name missing in stored TP Devices
                else:
                    tp_data = tp_devices[tp_device_name_key]
                    if "dev_id" not in tp_data:
                        valid = False  # Indigo Device id missing in TP device
                    else:
                        try:
                            indigo_device_id = int(tp_data["dev_id"])
                            if indigo_device_id not in indigo.devices:
                                valid = False  # Indigo Device id not known to Indigo
                        except ValueError:
                            valid = False  # Indigo Device id stored in TP device is invalid
                if not valid:
                    self.tph_logger.error(
                        "Action '{0}' received from Touch Portal Desktop App for invalid TP Device '{1}'.".format(
                            TP_ENTRY_TRANSLATION[tp_action], tp_device_name))
                    return  # Invalid

                indigo_dev = indigo.devices[indigo_device_id]  # This is the Indigo Device upon which the TP action will be performed

                if indigo_dev.name == tp_device_name:
                    log_message_name = "'{0}'".format(indigo_dev.name)
                else:
                    log_message_name = "'{0}' [TP Name '{1}']".format(indigo_dev.name, tp_device_name)

                if tp_action == TP_ENTRY_COMMAND_DEVICE_TURN_ON:
                    if debug_show_messages_from_tp_desktop:
                        self.tph_logger.info("Action '{0}' received from Touch Portal Desktop App for Device {1}".format(
                                             TP_ENTRY_TRANSLATION[tp_action], log_message_name))
                    indigo.device.turnOn(indigo_device_id)

                elif tp_action == TP_ENTRY_COMMAND_DEVICE_TURN_OFF:
                    if debug_show_messages_from_tp_desktop:
                        self.tph_logger.info("Action '{0}' received from Touch Portal Desktop App for Device {1}".format(
                                             TP_ENTRY_TRANSLATION[tp_action], log_message_name))
                    indigo.device.turnOff(indigo_device_id)

                elif tp_action == TP_ENTRY_COMMAND_DEVICE_TOGGLE:
                    if debug_show_messages_from_tp_desktop:
                        self.tph_logger.info("Action '{0}' received from Touch Portal Desktop App for Device {1}".format(
                                             TP_ENTRY_TRANSLATION[tp_action], log_message_name))
                    indigo.device.toggle(indigo_device_id)

                elif tp_action == TP_ENTRY_COMMAND_DEVICE_BRIGHTNESS_SET:
                    valid = True  # Assume valid request
                    try:
                        if tp_brightness_value is None or tp_brightness_value == "":
                            tp_brightness_value = "?"
                            valid = False
                        else:
                            tp_brightness_value = int(tp_brightness_value)
                    except ValueError:
                        valid = False
                    if valid and tp_brightness_value < 0 or tp_brightness_value > 100:
                        valid = False
                    if not valid:
                        if tp_brightness_value == "?":
                            self.tph_logger.error(
                                "Action '{0}' received from Touch Portal Desktop App for Device {1} with no brightness value specified".format(
                                    TP_ENTRY_TRANSLATION[tp_action], log_message_name))
                            return  # Invalid
                        else:
                            self.tph_logger.error(u"Action '{0}' to {1}% received from Touch Portal Desktop App for Device {2} is invalid - it must be an integer and between 0 and "
                                                  u"100 (inclusive)".format(TP_ENTRY_TRANSLATION[tp_action], tp_brightness_value, log_message_name))
                        return  # Invalid
                    if debug_show_messages_from_tp_desktop:
                        self.tph_logger.info(
                            "Action '{0}' to {1}% received from Touch Portal Desktop App for Device {2}".format(
                                TP_ENTRY_TRANSLATION[tp_action], tp_brightness_value, log_message_name))
                    indigo.dimmer.setBrightness(indigo_device_id, value=tp_brightness_value)

                elif tp_action == TP_ENTRY_COMMAND_DEVICE_BRIGHTEN:
                    valid = True  # Assume valid request
                    try:
                        if tp_brighten_value is None or tp_brighten_value == "":
                            tp_brighten_value = "?"
                            valid = False
                        else:
                            tp_brighten_value = int(tp_brighten_value)
                    except ValueError:
                        valid = False
                    if valid and tp_brighten_value < 1 or tp_brighten_value > 100:
                        valid = False
                    if not valid:
                        if tp_brighten_value == "?":
                            self.tph_logger.error(
                                "Action '{0}' received from Touch Portal Desktop App for Device {1} with no brighten value specified".format(
                                    TP_ENTRY_TRANSLATION[tp_action], log_message_name))
                            return  # Invalid
                        else:
                            self.tph_logger.error(u"Action '{0}' by {1}% received from Touch Portal Desktop App for Device '{2}' is invalid - it must be an integer and between 1 and "
                                                  u"100 (inclusive)".format(TP_ENTRY_TRANSLATION[tp_action], tp_brighten_value, log_message_name))
                        return  # Invalid
                    if debug_show_messages_from_tp_desktop:
                        self.tph_logger.info(
                            "Action '{0}' by {1}% received from Touch Portal Desktop App for Device {1}".format(
                                TP_ENTRY_TRANSLATION[tp_action], log_message_name))
                    indigo.dimmer.brighten(indigo_device_id, by=tp_brighten_value)

                elif tp_action == TP_ENTRY_COMMAND_DEVICE_DIM:
                    valid = True  # Assume valid request
                    try:
                        if tp_dim_value is None or tp_dim_value == "":
                            tp_dim_value = "?"
                            valid = False
                        else:
                            tp_dim_value = int(tp_dim_value)
                    except ValueError:
                        valid = False
                    if valid and tp_dim_value < 1 or tp_dim_value > 100:
                        valid = False
                    if not valid:
                        if tp_dim_value == "?":
                            self.tph_logger.error(
                                "Action '{0}' received from Touch Portal Desktop App for Device {1} with no dim value specified".format(
                                    TP_ENTRY_TRANSLATION[tp_action], log_message_name))
                            return  # Invalid
                        else:
                            self.tph_logger.error(u"Action '{0}' by {1}% received from Touch Portal Desktop App for Device {2} is invalid - it must be an integer and between 1 and "
                                                  u"100 (inclusive)".format(TP_ENTRY_TRANSLATION[tp_action], tp_dim_value, log_message_name))
                        return  # Invalid
                    if debug_show_messages_from_tp_desktop:
                        self.tph_logger.info("Action '{0}' by {1}% received from Touch Portal Desktop App for Device {2}".format(
                            TP_ENTRY_TRANSLATION[tp_action], tp_dim_value, log_message_name))
                    indigo.dimmer.dim(indigo_device_id, by=tp_dim_value)

                elif tp_action == TP_ENTRY_COMMAND_DEVICE_SET_COLOUR:
                    if not hasattr(indigo_dev, 'supportsRGB')\
                            or not hasattr(indigo_dev, 'supportsColor')\
                            or not indigo_dev.supportsRGB\
                            or not indigo_dev.supportsColor:  # Check device supports color
                        self.tph_logger.error("Action '{0}' received from Touch Portal Desktop App for Device {1} which does not support colour - action ignored".format(
                                TP_ENTRY_TRANSLATION[tp_action], log_message_name))
                        return  # Invalid

                    valid = True  # Assume valid request
                    if tp_colour_value is None or tp_colour_value == "":
                        tp_colour_value = "?"
                        valid = False
                    else:
                        # validate colour string which should be in hex format: '#rrggbbaa' ('aa' is transparency and will be ignored)
                        rgb_string = re.compile(r'#[a-fA-F0-9]{8}$')
                        if not bool(rgb_string.match(tp_colour_value)):
                            valid = False
                    if not valid:
                        if tp_colour_value == "?":
                            self.tph_logger.error(
                                "Action '{0}' received from Touch Portal Desktop App for Device {1} with no colour value specified".format(
                                    TP_ENTRY_TRANSLATION[tp_action], log_message_name))
                            return  # Invalid
                        else:
                            self.tph_logger.error(u"Action '{0}' received from Touch Portal Desktop App"
                                                  u" for Device {1}. '{2}' is invalid"
                                                  u" - it must be a color hex string format #rrggbbaa"
                                                  .format(TP_ENTRY_TRANSLATION[tp_action],
                                                          indigo_dev, indigo_color_value))
                        return  # Invalid
                    red_level = int(int(tp_colour_value[1:3], 16) * 100)
                    green_level = int(int(tp_colour_value[3:5], 16) * 100)
                    blue_level = int(int(tp_colour_value[5:7], 16) * 100)
                    if debug_show_messages_from_tp_desktop:
                        self.tph_logger.info("Action '{0}' received from Touch Portal Desktop App for Device {1}."
                                             "Set Colour to: Red = {2}, Green = {3}, Blue = {4}"
                                             .format(TP_ENTRY_TRANSLATION[tp_action], log_message_name,
                                                     red_level, green_level, blue_level))
                    indigo.dimmer.setColorLevels(indigo_device_id, red_level, green_level, blue_level)

            elif "action_group_" in tp_action and tp_action in TP_ENTRY_COMMANDS_ACTION_GROUP:
                if tp_action_group_name is None or tp_action_group_name == "":
                    self.tph_logger.error("Action '{0}' received from Touch Portal Desktop App"
                                          " with missing Touch Portal Device name"
                                          .format(TP_ENTRY_TRANSLATION[tp_action]))
                    return  # Invalid

                # validate request and determine related Indigo Action Group
                valid = True  # Assume valid request
                indigo_action_group_id = 0  # Only needed to suppress PyCharm 'referenced before assignment' warning

                tp_device_name_key = tp_action_group_name.lower()  # Key is lowercase
                if tp_device_name_key not in tp_devices:
                    valid = False  # TP Device name missing in stored TP Devices
                else:
                    tp_data = tp_devices[tp_device_name_key]
                    if "action_group_id" not in tp_data:
                        valid = False  # Indigo Action Group id missing in TP device
                    else:
                        try:
                            indigo_action_group_id = int(tp_data["action_group_id"])
                            if indigo_action_group_id not in indigo.actionGroups:
                                valid = False  # Indigo Action Group id not known to Indigo
                        except ValueError:
                            valid = False  # Indigo Action Group id stored in TP device is invalid
                if not valid:
                    self.tph_logger.error(
                        "Action '{0}' received from Touch Portal Desktop App for Invalid TP Device '{1}'".format(
                            TP_ENTRY_TRANSLATION[tp_action], tp_device_name))
                    return  # Invalid

                action_group_dev = indigo.actionGroups[indigo_action_group_id]  # This is the Indigo Action Group upon which the TP action will be performed

                if action_group_dev.name == tp_variable_name:
                    log_message_name = "'{0}'".format(action_group_dev.name)
                else:
                    log_message_name = "'{0}' [TP Name '{1}']".format(action_group_dev.name, tp_action_group_name)

                if tp_action == TP_ENTRY_COMMAND_ACTION_GROUP_RUN:
                    if debug_show_messages_from_tp_desktop:
                        self.tph_logger.info("Action '{0}' received from Touch Portal Desktop App to run Action Group {0}".format(
                            TP_ENTRY_TRANSLATION[tp_action], log_message_name))
                    indigo.actionGroup.execute(indigo_action_group_id)

            elif "variable_" in tp_action and tp_action in TP_ENTRY_COMMANDS_VARIABLE:
                if tp_variable_name is None or tp_variable_name == "":
                    self.tph_logger.error(
                        "Action '{0}' received from Touch Portal Desktop App with missing Touch Portal Device name".format(TP_ENTRY_TRANSLATION[tp_action]))
                    return  # Invalid

                # validate request and determine related Indigo Variable
                valid_code = 0  # Assume valid request
                indigo_variable_id = 0  # Only needed to suppress PyCharm 'referenced before assignment' warning

                tp_device_name_key = tp_variable_name.lower()  # Key is lowercase
                if tp_device_name_key not in tp_devices:
                    valid_code = 4  # TP Device name missing in stored TP Devices

                else:
                    tp_data = tp_devices[tp_device_name_key]
                    if "variable_id" not in tp_data:
                        valid_code = 8  # Indigo Variable id missing in TP device
                    else:
                        try:
                            indigo_variable_id = int(tp_data["variable_id"])
                            if indigo_variable_id not in indigo.variables:
                                valid_code = 12  # Indigo Variable id not known to Indigo
                        except ValueError:
                            valid_code = 16  # Indigo Variable id stored in TP device is invalid
                if valid_code != 0:
                    error_message = ""
                    if valid_code == 4:
                        error_message = (u"No Variable named '{0}'".format(tp_device_name_key))
                    elif valid_code == 8:
                        error_message = (u"No Variable id specified for variable '{0}'"
                                         .format(tp_device_name_key))
                    elif valid_code == 12 or valid_code == 16:
                        error_message = (u"Variable '{0}' has invalid id = '{1}'"
                                         .format(tp_device_name_key, indigo_variable_id))
                    else:
                        error_message = u"Unknown error reason!"

                    self.tph_logger.error(
                        "Action '{0}' received from Touch Portal Desktop App is in error: {1}"
                        .format(TP_ENTRY_TRANSLATION[tp_action], error_message))
                    return  # Invalid

                variable_dev = indigo.variables[indigo_variable_id]  # This is the Indigo Variable upon which the TP action will be performed

                if variable_dev.name == tp_variable_name:
                    log_message_name = "'{0}'".format(variable_dev.name)
                else:
                    log_message_name = "'{0}' [TP Name '{1}']".format(variable_dev.name, tp_variable_name)

                if variable_dev.readOnly:
                    self.tph_logger.warning(
                        "Action '{0}' received from Touch Portal Desktop App to update Read ONLY Variable '{1}'"
                        " - Update ignored."
                        .format(TP_ENTRY_TRANSLATION[tp_action], variable_dev.name))
                    return  # Invalid

                if tp_action == TP_ENTRY_COMMAND_VARIABLE_SET_TEXT:
                    if debug_show_messages_from_tp_desktop:
                        self.tph_logger.info("Action '{0}' received from Touch Portal Desktop App to set Variable value for {1} to '{2}'"
                                             .format(TP_ENTRY_TRANSLATION[tp_action],
                                                     log_message_name, indigo_variable_value))
                    if self.globals[K_TP][dev_id][K_SHOW_VARIABLE_VALUE]:
                        self.tph_logger.info("Setting Variable {0} to value '{1}'".format(log_message_name, tp_variable_value))
                    indigo.variable.updateValue(indigo_variable_id, value=tp_variable_value)

                elif tp_action == TP_ENTRY_COMMAND_VARIABLE_SET_TRUE:
                    if debug_show_messages_from_tp_desktop:
                        self.tph_logger.info("Action '{0}' received from Touch Portal Desktop App to set Variable {1} to 'true'".format(
                                             TP_ENTRY_TRANSLATION[tp_action], log_message_name, indigo_variable_value))
                    if self.globals[K_TP][dev_id][K_SHOW_VARIABLE_VALUE]:
                        self.tph_logger.info("Setting Variable {0} to value 'true'".format(log_message_name, tp_variable_value))
                    indigo.variable.updateValue(indigo_variable_id, value="true")

                elif tp_action == TP_ENTRY_COMMAND_VARIABLE_SET_FALSE:
                    if debug_show_messages_from_tp_desktop:
                        self.tph_logger.info("Action '{0}' received from Touch Portal Desktop App to set Variable {1} to FALSE".format(
                                             TP_ENTRY_TRANSLATION[tp_action], log_message_name, indigo_variable_value))
                    if self.globals[K_TP][dev_id][K_SHOW_VARIABLE_VALUE]:
                        self.tph_logger.info("Setting Variable {0} to value 'false'".format(log_message_name, tp_variable_value))
                    indigo.variable.updateValue(indigo_variable_id, value="false")

                elif tp_action == TP_ENTRY_COMMAND_VARIABLE_TOGGLE:
                    if debug_show_messages_from_tp_desktop:
                        if variable_dev.name == tp_variable_name:
                            self.tph_logger.info("Action '{0}' received from Touch Portal Desktop App"
                                                 " to Toggle Variable {1}"
                                                 .format(TP_ENTRY_TRANSLATION[tp_action], log_message_name))
                        else:
                            self.tph_logger.info("Action '{0}' received from Touch Portal Desktop App"
                                                 " to Toggle Variable {1}"
                                                 .format(TP_ENTRY_TRANSLATION[tp_action], log_message_name))


                    variable_value = indigo.variables[indigo_variable_id].value
                    if variable_value.lower() == "false":
                        variable_value = "true"
                    elif variable_value.lower() == "true":
                        variable_value = "false"
                    else:
                        self.tph_logger.error(
                            "Action '{0}' received from Touch Portal Desktop App to Toggle Indigo Variable {1}"
                            " which currently has a non-bool value: '{2}'"
                            .format(TP_ENTRY_TRANSLATION[tp_action], log_message_name, variable_value))

                    if self.globals[K_TP][dev_id][K_SHOW_VARIABLE_VALUE]:
                        self.tph_logger.info("Setting Variable {0} to value '{1}'"
                                             .format(log_message_name, variable_value))
                    indigo.variable.updateValue(indigo_variable_id, value=variable_value)

            else:
                self.tph_logger.error(
                    "Action '{0}' received from Touch Portal Desktop App not recognised'".format(
                        tp_action))

        except StandardError as standard_error_message:
            self.tph_logger.error(u"StandardError detected in 'processReceiveTpMessageAction'."
                                  " Line '{0}' has error='{1}'"
                                  .format(sys.exc_traceback.tb_lineno, standard_error_message))

    # =============================================================================
    def process_receive_tp_message_info(self, dev, converted_data):
        """
        Process message received from Touch Portal Desktop.
        Process as appropriate: Indigo device/action group/variable command

        -----
        :param dev:
        :param converted_data:
        :return:
        """

        try:
            dev_id = dev.id

            #  Message in format: {"tpVersionString": "2.2.000", "tpVersionCode": 202000, "sdkVersion": 2, "type": "info", "pluginVersion": 43}

            try:
                tpVersion = converted_data["tpVersionString"]
            except StandardError:
                tpVersion = "Unknown"

            try:
                sdkVersion = int(converted_data["sdkVersion"])
            except StandardError:
                sdkVersion = 0

            try:
                pluginVersion = int(converted_data["pluginVersion"])
            except StandardError:
                pluginVersion = 0

            communication_established_ui = "\n"  # Start with a line break
            communication_established_ui += u"{0:={1}60}\n".format(" Touch Portal Desktop Info", "^")
            communication_established_ui += u"{0:<12} {1}\n".format("Version:", tpVersion)
            communication_established_ui += u"{0:<12} {1}\n".format("SDK:", sdkVersion)
            communication_established_ui += u"{0:<12} {1}\n".format("Plugin:", pluginVersion)
            communication_established_ui += u"{0:={1}60}\n".format("", "^")
            self.tph_logger.debug(communication_established_ui)

            try:
                if self.globals[K_TP_PLUGIN_INFO][K_TP_PLUGIN_VERSION] != 0:  # Will be zero if unable to determine required version from Indigo plugin version
                    if self.globals[K_TP_PLUGIN_INFO][K_TP_PLUGIN_VERSION] != pluginVersion:
                        self.tph_logger.warning(u"Touch Portal plugin version mismatch. Has the Touch Portal Desktop been restarted?")
            except StandardError:
                self.tph_logger.warning(u"Unable to verify Touch Portal plugin version")

            keyValueList = [
                {"key": "touch_portal_version", "value": tpVersion},
                {"key": "touch_portal_sdk_version", "value": sdkVersion},
                {"key": "touch_portal_plugin_version", "value": pluginVersion}
            ]
            dev.updateStatesOnServer(keyValueList)

            # Update Indigo TP device's firmware field (if necessary)
            if self.globals[K_TP_PLUGIN_INFO][K_TP_PLUGIN_VERSION] == pluginVersion:
                firmware = u"{0}".format(pluginVersion)
            else:
                firmware = u"{0}-{1}".format(self.globals[K_TP_PLUGIN_INFO][K_TP_PLUGIN_VERSION], pluginVersion)
            pluginProps = dev.pluginProps
            if "version" not in pluginProps or firmware != pluginProps["version"]:
                pluginProps["version"] = firmware
                dev.replacePluginPropsOnServer(pluginProps)

            self.process_refresh_tp_states(dev_id)

        except StandardError as standard_error_message:
            self.tph_logger.error(u"StandardError detected in 'process_receive_tp_message_info'. Line '{0}' has error='{1}'".format(sys.exc_traceback.tb_lineno, standard_error_message))

    # =============================================================================
    def process_receive_tp_message_list_change(self, dev, converted_data):
        """
        TODO: Complete this documentation!

        -----
        :param dev:
        :param converted_data:
        :return:
        """

        try:
            dev_id = dev.id

            # {"listId": "device_name", "instanceId": "u869rzy690oox", "pluginId": "indigo_domotics_001",
            #  "actionId": "device_turn_on_test", "type": "listChange", "value": "Lamp [East]"}

            tp_action_id = None
            tp_list_id = None
            tp_list_instance_id = None
            tp_list_change_value = None

            self.tph_logger.debug(u"LIST CHANGE: Converted Data [{0}] = '{1}'".format(type(converted_data), converted_data))

            if "actionId" in converted_data:
                tp_action_id = converted_data["actionId"]
            if "listId" in converted_data:
                tp_list_id = converted_data["listId"]
            if "instanceId" in converted_data:
                tp_list_instance_id = converted_data["instanceId"]
            if "value" in converted_data:
                tp_list_change_value = converted_data["value"]

            if tp_list_instance_id is None:
                return

            tp_devices_pre_json = dev.pluginProps.get("tp_devices", None)
            if tp_devices_pre_json is None:
                self.tph_logger.warning(u"TP DEVICES MISSING")  # TODO: Needs Enhancing
                return
            tp_devices = json.loads(tp_devices_pre_json)

            tp_devices_list = ""
            if tp_list_id == "indigo_device_name_on_off" and tp_list_change_value == "- Refresh Devices -":
                if (tp_action_id == TP_ENTRY_COMMAND_DEVICE_TURN_ON or
                        tp_action_id == TP_ENTRY_COMMAND_DEVICE_TURN_OFF or
                        tp_action_id == TP_ENTRY_COMMAND_DEVICE_TOGGLE):
                    tp_devices_supporting_on_off = list()
                    for tp_name_key, tp_data in tp_devices.iteritems():
                        if tp_data["mode"] == 'D':
                            if "supports_on_off_state" in tp_data and bool(tp_data["supports_on_off_state"]):
                                tp_devices_supporting_on_off.append(tp_data["tp_name"])
                    if len(tp_devices_supporting_on_off) == 0:
                        tp_devices_list = '"- No Devices Defined -"'
                    else:
                        tp_devices_list = '"- Select Device -"'
                        for tp_device_supporting_on_off in tp_devices_supporting_on_off:
                            tp_devices_list += u', "{0}"'.format(tp_device_supporting_on_off)
                    tp_devices_list += u', "- Refresh Devices -"'

            elif tp_list_id == "indigo_device_name_brightness" and tp_list_change_value == "- Refresh Devices -":
                if (tp_action_id == TP_ENTRY_COMMAND_DEVICE_BRIGHTNESS_SET or
                        tp_action_id == TP_ENTRY_COMMAND_DEVICE_BRIGHTEN or
                        tp_action_id == TP_ENTRY_COMMAND_DEVICE_DIM):
                    tp_devices_supporting_brightness = list()
                    for tp_name_key, tp_data in tp_devices.iteritems():
                        if tp_data["mode"] == 'D':
                            if "supports_brightness_state" in tp_data and bool(tp_data["supports_brightness_state"]):
                                tp_devices_supporting_brightness.append(tp_data["tp_name"])
                    if len(tp_devices_supporting_brightness) == 0:
                        tp_devices_list = '"- No Devices Defined -"'
                    else:
                        tp_devices_list = '"- Select Device -"'
                        for tp_device_supporting_brightness in tp_devices_supporting_brightness:
                            tp_devices_list += u', "{0}"'.format(tp_device_supporting_brightness)
                    tp_devices_list += u', "- Refresh Devices -"'

            elif tp_list_id == "indigo_device_name_rgb" and tp_list_change_value == "- Refresh Devices -":
                if tp_action_id == TP_ENTRY_COMMAND_DEVICE_SET_COLOUR:
                    tp_devices_supporting_rgb = list()
                    for tp_name_key, tp_data in tp_devices.iteritems():
                        if tp_data["mode"] == 'D':
                            if "supports_brightness_state" in tp_data and bool(
                                    tp_data["supports_colourRGB_state"]):
                                tp_devices_supporting_rgb.append(tp_data["tp_name"])
                    if len(tp_devices_supporting_rgb) == 0:
                        tp_devices_list = '"- No Devices Defined -"'
                    else:
                        tp_devices_list = '"- Select Device -"'
                        for tp_device_supporting_rgb in tp_devices_supporting_rgb:
                            tp_devices_list += u', "{0}"'.format(tp_device_supporting_rgb)
                    tp_devices_list += u', "- Refresh Devices -"'

            elif tp_list_id == "indigo_action_group_name" and tp_list_change_value == "- Refresh Action Groups -":
                if tp_action_id == TP_ENTRY_COMMAND_ACTION_GROUP_RUN:
                    tp_devices_action_group = list()
                    for tp_name_key, tp_data in tp_devices.iteritems():
                        if tp_data["mode"] == 'A':
                            tp_devices_action_group.append(tp_data["tp_name"])
                    if len(tp_devices_action_group) == 0:
                        tp_devices_list = '"- No Action Groups Defined -"'
                    else:
                        tp_devices_list = '"- Select Action Group -"'
                        for tp_device_action_group in tp_devices_action_group:
                            tp_devices_list += u', "{0}"'.format(tp_device_action_group)
                    tp_devices_list += u', "- Refresh Action Groups -"'

            elif tp_list_id == "indigo_variable_name_text" and tp_list_change_value == "- Refresh Variables -":
                if tp_action_id == TP_ENTRY_COMMAND_VARIABLE_SET_TEXT:
                    tp_devices_variable = list()
                    for tp_name_key, tp_data in tp_devices.iteritems():
                        if tp_data["mode"] == 'V':
                            if tp_data["supports_variable_tp_text_state"]:
                                tp_devices_variable.append(tp_data["tp_name"])
                    if len(tp_devices_variable) == 0:
                        tp_devices_list = '"- No Variables Defined -"'
                    else:
                        tp_devices_list = '"- Select Variable -"'
                        for tp_device_variable in tp_devices_variable:
                            tp_devices_list += u', "{0}"'.format(tp_device_variable)
                    tp_devices_list += u', "- Refresh Variables -"'

            elif tp_list_id == "indigo_variable_name_true_false" and tp_list_change_value == "- Refresh Variables -":
                if (tp_action_id == TP_ENTRY_COMMAND_VARIABLE_SET_TRUE
                        or tp_action_id == TP_ENTRY_COMMAND_VARIABLE_SET_FALSE
                        or tp_action_id == TP_ENTRY_COMMAND_VARIABLE_TOGGLE):
                    tp_devices_variable = list()
                    for tp_name_key, tp_data in tp_devices.iteritems():
                        if tp_data["mode"] == 'V':
                            if tp_data["supports_variable_tp_true_false_state"]:
                                tp_devices_variable.append(tp_data["tp_name"])
                    if len(tp_devices_variable) == 0:
                        tp_devices_list = '"- No Variables Defined -"'
                    else:
                        tp_devices_list = '"- Select Variable -"'
                        for tp_device_variable in tp_devices_variable:
                            tp_devices_list += u', "{0}"'.format(tp_device_variable)
                    tp_devices_list += u', "- Refresh Variables -"'

            else:
                return  # Ignore as not a Refresh

            self.tph_logger.debug(
                u"TP NEW CHOICES: Converted Data [{0}] = '{1}'".format(type(tp_devices_list), tp_devices_list))

            tp_message = '{{"type": "choiceUpdate", "id": "{0}", "instanceId": "{1}", "value" : [{2}]}}'.format(tp_list_id, tp_list_instance_id, tp_devices_list)

            # self.globals[K_QUEUES][dev_id][K_SEND_TO_TP].put([QUEUE_PRIORITY_HIGH, 0, CMD_PROCESS_SEND_TP_MESSAGE, dev_id, [tp_message]])

            self.process_send_tp_message(dev_id, tp_message)

            self.tph_logger.debug(
                u"TP MESSAGE: Converted Data [{0}] = '{1}'".format(type(tp_message), tp_message))

        except StandardError as standard_error_message:
            self.tph_logger.error(u"StandardError detected in 'process_receive_tp_message_list_change'. Line '{0}' has error='{1}'".format(sys.exc_traceback.tb_lineno,
                                                                                                                                           standard_error_message))

    # =============================================================================
    def process_refresh_tp_states(self, dev_id):
        """
        TODO: Complete this documentation!

        -----
        :param:
        :return:
        """

        try:
            for monitor_dev_id, monitor_list in self.globals[K_TP][K_MONITORED_DEVICES].iteritems():
                monitored_dev = indigo.devices[monitor_dev_id]
                tp_desktop_device_id = monitor_list[TP_MONITOR_TP_DESKTOP_DEV_ID]
                if dev_id is None or dev_id == tp_desktop_device_id:
                    # tp_state_id = monitor_list[TP_MONITOR_TP_STATE_ID]  # TODO: Remove this line once confirmed as OK
                    monitor_on_off = monitor_list[TP_MONITOR_ON_OFF]
                    monitor_brightness = monitor_list[TP_MONITOR_BRIGHTNESS]
                    monitor_rgb = monitor_list[TP_MONITOR_RGB]

                    if monitor_on_off:
                        self.tph_logger.debug(
                            u"K_MONITORED_DEVICE [ON_OFF]:\n{0}\n".format(self.globals[K_TP][K_MONITORED_DEVICES]))
                        new_state_value = "OFF"
                        if monitored_dev.onState:
                            new_state_value = "ON"
                        tp_state_id = u"indigo_device_{0}_on_off".format(monitor_dev_id)
                        tp_message = '{{"type": "stateUpdate", "id": "{0}", "value" : "{1}"}}'.format(
                            tp_state_id, new_state_value)

                        self.process_send_tp_message(tp_desktop_device_id, tp_message)

                    if monitor_brightness:
                        self.tph_logger.debug(
                            u"K_MONITORED_DEVICE [BRIGHTNESS]:\n{0}\n".format(self.globals[K_TP][K_MONITORED_DEVICES]))
                        new_state_value = monitored_dev.brightness
                        tp_state_id = u"indigo_device_{0}_brightness".format(monitor_dev_id)
                        tp_message = '{{"type": "stateUpdate", "id": "{0}", "value" : "{1}"}}'.format(
                            tp_state_id, new_state_value)

                        self.process_send_tp_message(tp_desktop_device_id, tp_message)

                    if monitor_rgb:
                        self.tph_logger.debug(
                            u"K_MONITORED_DEVICE [COLOUR RGB]:\n{0}\n".format(self.globals[K_TP][K_MONITORED_DEVICES]))
                        red_level = int((monitored_dev.redLevel * 255.0) / 100.0)
                        green_level = int((monitored_dev.greenLevel * 255.0) / 100.0)
                        blue_level = int((monitored_dev.blueLevel * 255.0) / 100.0)
                        new_state_value = ('#FF%02x%02x%02x' % (red_level, green_level, blue_level)).upper()
                        tp_state_id = u"indigo_device_{0}_colour_rgb".format(monitor_dev_id)
                        tp_message = '{{"type": "stateUpdate", "id": "{0}", "value" : "{1}"}}'.format(
                            tp_state_id, new_state_value)

                        self.process_send_tp_message(tp_desktop_device_id, tp_message)

                    # TODO: Add in Refresh of variable state (Text  and True / False)

        except StandardError as standard_error_message:
            self.tph_logger.error(u"StandardError detected in Touch Portal Plugin [deviceUpdated] for device '???']. Line '{0}' has error='{1}'".format(
                                     sys.exc_traceback.tb_lineno, standard_error_message))

    # =============================================================================
    def process_send_tp_message(self, dev_id, message_to_send):
        """
        Process message to send to Touch Portal Desktop.

        -----
        :param dev_id:
        :param message_to_send:
        :return:
        """
        try:
            reformatted_message = b"{0}\n".format(message_to_send)

            try:
                self.globals[K_SOCKETS][dev_id][K_TP_SOCKET].sendall(reformatted_message)
            except socket.error as socket_error_info:
                if socket_error_info.errno == 32:  # Broken Pipe
                    self.tph_logger.debug(
                        u"Socket error detected when sending message to Touch Portal Desktop: Is it running?")
                    self.tph_logger.debug(
                        u"Unable to send message '{0}' to Touch Portal Desktop.".format(message_to_send))
                else:
                    self.tph_logger.error(
                        u"Socket Error detected in 'process_send_tp_message'. Line '{0}' has error='{1}'.".format(
                            sys.exc_traceback.tb_lineno, socket_error_info))

            self.tph_logger.debug(u"process_send_tp_message: {0}".format(reformatted_message))

        except StandardError as standard_error_message:
            self.tph_logger.error(u"StandardError detected in 'process_send_tp_message'. Line '{0}' has error='{1}'".format(sys.exc_traceback.tb_lineno, standard_error_message))

    # =============================================================================
    def run(self):
        """
        Run thread.
        """
        try:
            # Initialise routine on thread start

            dev_id = self.dev_id
            dev = indigo.devices[dev_id]

            self.globals[K_QUEUES][dev_id][K_RECEIVE_FROM_SEND_TO_TP].put([QUEUE_PRIORITY_HIGH, 0, CMD_PROCESS_SEND_TP_MESSAGE, dev_id, ['{"type":"pair", "id":"indigo_domotics_001"}']])

            self.tph_logger.debug(u"Touch Portal Handler Thread initialised")

            self.handle_communication(dev)

        except StandardError as standard_error_message:
            self.tph_logger.error(u"StandardError detected in TP Handler Thread. Line '{0}' has error='{1}'".format(sys.exc_traceback.tb_lineno, standard_error_message))

        self.tph_logger.debug(u"Touch Portal Handler Thread Ended")
