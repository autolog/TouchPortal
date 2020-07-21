#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Touch Portal © Autolog & DaveL17 2020


# noinspection PyUnresolvedReferences
# ============================== Native Imports ===============================
import datetime
import json
import logging
import os
import platform
import Queue
import shutil
import sys
import threading
from tpHandler import ThreadTpHandler
from tpReader import ThreadTpReader

# ============================== Custom Imports ===============================
try:
    import indigo
except ImportError:
    pass

# ============================== Plugin Imports ===============================
from constants import *
import entry_tp_generator


# noinspection PyUnresolvedReferences
class Plugin(indigo.PluginBase):

    # =============================================================================
    def __init__(self, plugin_id, plugin_display_name, plugin_version, plugin_prefs):

        indigo.PluginBase.__init__(self, plugin_id, plugin_display_name, plugin_version, plugin_prefs)

        self.stopThread = False  # Used to stop Concurrent Thread

        # Initialise dictionary to store plugin Globals aka plugin working storage
        self.globals = {}

        # Initialise Indigo plugin info
        self.globals[K_PLUGIN_INFO] = {}
        self.globals[K_PLUGIN_INFO][K_PLUGIN_ID] = plugin_id
        self.globals[K_PLUGIN_INFO][K_PLUGIN_DISPLAY_NAME] = plugin_display_name
        self.globals[K_PLUGIN_INFO][K_PLUGIN_VERSION] = plugin_version
        self.globals[K_PLUGIN_INFO][K_PATH] = indigo.server.getInstallFolderPath()  # e.g. '/Library/Application Support/Perceptive Automation/Indigo 7.4'
        self.globals[K_PLUGIN_INFO][K_API_VERSION] = indigo.server.apiVersion
        self.globals[K_PLUGIN_INFO][K_ADDRESS] = indigo.server.address

        # Initialise Indigo plugin info
        self.globals[K_TP_PLUGIN_INFO] = {}
        try:
            self.globals[K_TP_PLUGIN_INFO][K_TP_PLUGIN_VERSION] = int(self.globals[K_PLUGIN_INFO][K_PLUGIN_VERSION].split(".")[2])
        except StandardError:
            indigo.server.log(u"Indigo Touch Portal Plugin Version error - "
                              u"'{0}' is not in the correct format - "
                              u"Unable to check Touch Portal Desktop version!".format(self.globals[K_PLUGIN_INFO][K_PLUGIN_VERSION]), isError=True)
            self.globals[K_TP_PLUGIN_INFO][K_TP_PLUGIN_VERSION] = 0

        # Initialise dictionary for debug log levels in plugin Globals
        self.globals[K_DEBUG] = {}
        self.globals[K_DEBUG][K_SHOW_MESSAGES] = TP_SHOW_MESSAGES_DEFAULT

        # Setup Logging - Logging info:
        #   self.indigo_log_handler - writes log messages to Indigo Event Log
        #   self.plugin_file_handler - writes log messages to the plugin log

        log_format = logging.Formatter("%(asctime)s.%(msecs)03d\t%(levelname)-12s\t%(name)s.%(funcName)-25s %(msg)s", datefmt="%Y-%m-%d %H:%M:%S")
        self.plugin_file_handler.setFormatter(log_format)
        self.plugin_file_handler.setLevel(K_LOG_LEVEL_INFO)  # Logging Level for plugin log file
        self.indigo_log_handler.setLevel(K_LOG_LEVEL_INFO)   # Logging level for Indigo Event Log

        self.logger = logging.getLogger("Plugin.TP")

        # Now logging is set-up, output Initialising Message
        startup_message_ui = "\n"  # Start with a line break
        startup_message_ui += u"{0:={1}130}\n".format(" Initialising Touch Portal Plugin ", "^")
        startup_message_ui += u"{0:<31} {1}\n".format("Plugin Name:", self.globals[K_PLUGIN_INFO][K_PLUGIN_DISPLAY_NAME])
        startup_message_ui += u"{0:<31} {1}\n".format("Plugin Version:", self.globals[K_PLUGIN_INFO][K_PLUGIN_VERSION])
        startup_message_ui += u"{0:<31} {1}\n".format("Plugin ID:", self.globals[K_PLUGIN_INFO][K_PLUGIN_ID])
        startup_message_ui += u"{0:<31} {1}\n".format("Indigo Version:", indigo.server.version)
        startup_message_ui += u"{0:<31} {1}\n".format("Indigo API Version:", indigo.server.apiVersion)
        startup_message_ui += u"{0:<31} {1}\n".format("Python Version:", sys.version.replace("\n", ""))
        startup_message_ui += u"{0:<31} {1}\n".format("Mac OS Version:", platform.mac_ver()[0])
        startup_message_ui += u"{0:={1}130}\n".format("", "^")
        self.logger.info(startup_message_ui)

        # Initialise dictionary to store internal details about Touch Portal devices
        self.globals[K_TP] = {}

        # Initialise dictionary to store message queues
        self.globals[K_QUEUES] = {}

        # Initialise dictionary to store threads
        self.globals[K_THREADS] = {}

        # Initialise dictionary to store sockets
        self.globals[K_SOCKETS] = {}

        # Initialise dictionary for socket recovery
        self.globals[K_RECOVERY_INVOKED] = []  # A list of device Ids to recover socket connections for - likely to only be one item in list!

        self.globals[K_LOCK] = threading.Lock()  # Used to serialise updating of 'recoveryInvoked'

        # Initialise dictionary for constants
        self.globals[K_CONSTANT] = {}
        self.globals[K_CONSTANT][K_DEFAULT_DATE_TIME] = datetime.datetime.strptime("2000-01-01", "%Y-%m-%d")

        # Initialise monitored devices and monitored variables
        self.globals[K_TP][K_MONITORED_DEVICES] = {}  # Dictionary will be filled with devices to monitor
        self.globals[K_TP][K_MONITORED_VARIABLES] = {}  # Dictionary will be filled with variables to monitor

        # Set Plugin Config Values
        self.closedPrefsConfigUi(plugin_prefs, False)

        self.stopThread = False

    # =============================================================================
    def __del__(self):

        indigo.PluginBase.__del__(self)

    # =============================================================================
    def actionControlDevice(self, action, dev):
        """
        Indigo method for device callbacks.

        Actions invoked to connect / disconnect from Touch Portal Desktop and toggle connection.

        -----
        :param action:
        :param dev:
        :return:

        """

        # Connect
        if action.deviceAction == indigo.kDeviceAction.TurnOn:
            self.process_turn_on(dev, False)  # False = No Toggle

        # Disconnect
        elif action.deviceAction == indigo.kDeviceAction.TurnOff:
            self.process_turn_off(dev, False)  # False = No Toggle

        # Toggle connection
        elif action.deviceAction == indigo.kDeviceAction.Toggle:
            desired_on_state = not dev.onState
            if desired_on_state:
                self.process_turn_on(dev, True)  # True = Toggle
            else:
                self.process_turn_off(dev, True)  # True = Toggle

    # =============================================================================
    def closedDeviceConfigUi(self, values_dict, user_cancelled, type_id, dev_id):
        """
        Indigo method invoked after device configuration dialog is closed.

        -----
        :param values_dict:
        :param user_cancelled:
        :param type_id:
        :param dev_id:
        :return:
        """

        try:
            if user_cancelled:
                self.logger.debug(u"'closedDeviceConfigUi' called with userCancelled = {0}".format(str(user_cancelled)))
                return

            # Following properties saved in globals as a device start is not required when
            # they are updated. A device start is required when the other properties that
            # do require a start are altered i.e. host/port/timeout.

            if dev_id not in self.globals[K_TP]:
                self.globals[K_TP][dev_id] = {}
            self.globals[K_TP][dev_id][K_SHOW_VARIABLE_VALUE] = bool(values_dict.get("show_variable_value", TP_SHOW_VARIABLE_VALUE_DEFAULT))
            self.globals[K_TP][dev_id][K_AUTO_CONNECT] = bool(values_dict.get("auto_connect", TP_AUTO_CONNECT_DEFAULT))
            self.globals[K_TP][dev_id][K_SOCKET_RETRY_SECONDS] = int(values_dict.get("socket_retry_seconds", TP_SOCKET_RETRY_DEFAULT))
            self.globals[K_TP][dev_id][K_SOCKET_RETRY_SILENT_AFTER] = int(values_dict.get("socket_retry_silent_after", TP_SOCKET_RETRY_SILENT_AFTER_DEFAULT))

        except StandardError as standard_error_message:
            self.logger.error(u"closedDeviceConfigUi error detected. "
                              u"Line '{0}' has error='{1}'".format(sys.exc_traceback.tb_lineno,
                                                                   standard_error_message))
            return True

    # =============================================================================
    def closedPrefsConfigUi(self, values_dict, user_cancelled):
        """
        Indigo method invoked after plugin configuration dialog is closed.

        -----
        :param values_dict:
        :param user_cancelled:
        :return:
        """

        try:
            if user_cancelled:
                return

            # Get required Event Log and Plugin Log logging levels
            plugin_log_level = int(values_dict.get("pluginLogLevel", K_LOG_LEVEL_INFO))
            event_log_level = int(values_dict.get("eventLogLevel", K_LOG_LEVEL_INFO))

            # Ensure following logging level messages are output
            self.indigo_log_handler.setLevel(K_LOG_LEVEL_INFO)
            self.plugin_file_handler.setLevel(K_LOG_LEVEL_INFO)

            # Output required logging levels and TP Message Monitoring requirement to logs
            self.globals[K_DEBUG][K_SHOW_MESSAGES] = bool(values_dict.get("showMessages", TP_SHOW_MESSAGES_DEFAULT))
            self.logger.debug(u"Show Messages from Touch Portal set to {0}".format(self.globals[K_DEBUG][K_SHOW_MESSAGES]))
            self.logger.info(u"Logging to Indigo Event Log at the '{0}' level".format(K_LOG_LEVEL_TRANSLATION[event_log_level]))
            self.logger.info(u"Logging to Plugin Event Log at the '{0}' level".format(K_LOG_LEVEL_TRANSLATION[plugin_log_level]))

            # Now set required logging levels
            self.indigo_log_handler.setLevel(event_log_level)
            self.plugin_file_handler.setLevel(plugin_log_level)

        except StandardError as standard_error_message:
            self.logger.error(u"'closedPrefsConfigUi' error detected. "
                              u"Line '{0}' has error='{1}'".format(sys.exc_traceback.tb_lineno,
                                                                   standard_error_message))
            return True

    # =============================================================================
    def deviceStartComm(self, dev):
        """
        Indigo method invoked when plugin device is started.

        -----
        :param dev:
        :return:
        """

        try:
            dev.stateListOrDisplayStateIdChanged()  # Ensure latest devices.xml is being used

            dev_id = dev.id

            self.logger.debug(u"Starting '{0}' device".format(dev.name))

            if dev_id not in self.globals[K_TP]:
                self.globals[K_TP][dev_id] = {}
            self.globals[K_TP][dev_id][K_DEVICE_STARTED] = False

            self.globals[K_TP][dev_id][K_HOST] = dev.pluginProps.get("host", TP_HOST_DEFAULT)
            self.globals[K_TP][dev_id][K_PORT] = int(dev.pluginProps.get("port", TP_PORT_DEFAULT))
            self.globals[K_TP][dev_id][K_DESKTOP_USER_DATA_FOLDER_PATH] = dev.pluginProps.get("tp_user_data_folder_path", None)
            self.globals[K_TP][dev_id][K_TIMEOUT] = int(dev.pluginProps.get("timeout", TP_SOCKET_TIMEOUT_DEFAULT))
            self.globals[K_TP][dev_id][K_SOCKET_RETRY_SECONDS] = int(dev.pluginProps.get("socket_retry_seconds", TP_SOCKET_RETRY_DEFAULT))
            self.globals[K_TP][dev_id][K_SOCKET_RETRY_SILENT_AFTER] = int(dev.pluginProps.get("socket_retry_silent_after", TP_SOCKET_RETRY_SILENT_AFTER_DEFAULT))
            self.globals[K_TP][dev_id][K_SHOW_VARIABLE_VALUE] = bool(dev.pluginProps.get("show_variable_value", TP_SHOW_VARIABLE_VALUE_DEFAULT))

            # Check and set device address to host IP
            if dev.address != self.globals[K_TP][dev_id][K_HOST]:
                new_props = dev.pluginProps
                new_props["address"] = self.globals[K_TP][dev_id][K_HOST]
                dev.replacePluginPropsOnServer(new_props)

            # On device start - if default entry.tp location is None or empty, populate it.
            if self.globals[K_TP][dev_id][K_DESKTOP_USER_DATA_FOLDER_PATH] in ("", None):
                self.globals[K_TP][dev_id][K_DESKTOP_USER_DATA_FOLDER_PATH] = u"{0}{1}".format(os.path.expanduser("~"), TP_DESKTOP_USER_DATA_FOLDER_DEFAULT_PATH)

            # Check if Touch Portal is installed and/or the Touch Portal User Data Folder is specified correctly
            if not os.path.isdir(self.globals[K_TP][dev_id][K_DESKTOP_USER_DATA_FOLDER_PATH]):
                #  It is missing!
                self.logger.error(
                    u"User Data folder not found for Touch Portal device '{0}': '{1}'".format(
                        dev.name, self.globals[K_TP][dev_id][K_DESKTOP_USER_DATA_FOLDER_PATH]))
                return  # Can't start device
            else:
                # Touch Portal User Data Folder exists - check it is for real by checking for specific folder contained within it
                validity_check_folder = u"{0}/{1}".format(self.globals[K_TP][dev_id][K_DESKTOP_USER_DATA_FOLDER_PATH], TP_DESKTOP_VALIDITY_CHECK_FOLDER)
                if not os.path.isdir(validity_check_folder):
                    #  validity_check_folder is missing!
                    self.logger.error(
                        u"User Data folder not valid for Touch Portal device '{0}': '{1}'".format(
                            dev.name, self.globals[K_TP][dev_id][K_DESKTOP_USER_DATA_FOLDER_PATH]))
                    return  # Can't start device

            # Touch Portal User Data folder found and valid - make sure plugin props is up-to-date
            new_props = dev.pluginProps
            if new_props["tp_user_data_folder_path"] != self.globals[K_TP][dev_id][K_DESKTOP_USER_DATA_FOLDER_PATH]:
                new_props["tp_user_data_folder_path"] = self.globals[K_TP][dev_id][K_DESKTOP_USER_DATA_FOLDER_PATH]
                dev.replacePluginPropsOnServer(new_props)

            # Touch Portal User Data folder found and valid - now check plugin is setup correctly
            plugin_path = u"{0}/{1}".format(self.globals[K_TP][dev_id][K_DESKTOP_USER_DATA_FOLDER_PATH], TP_DESKTOP_PLUGIN_LOCATION)
            if not os.path.isdir(plugin_path):
                os.makedirs(plugin_path)  # create plugin path if missing

            tp_plugin_icon_path_filename = u"{0}/{1}".format(plugin_path, TP_DESKTOP_PLUGIN_ICON_FILENAME)

            if not os.path.isfile(tp_plugin_icon_path_filename):
                # if missing, copy icon from Indigo plugin resources to TP plugin folder
                self.logger.debug(u"TP_PLUGIN_ICON_PATH_FILENAME: {0}".format(tp_plugin_icon_path_filename))

                source = u"{0}/{1}".format(self.globals[K_PLUGIN_INFO][K_PATH], TP_RESOURCES_ICON_PATH_FILENAME)
                target = u"{0}/{1}".format(plugin_path, TP_DESKTOP_PLUGIN_ICON_FILENAME)

                self.logger.debug(u"SOURCE: {0}".format(source))
                self.logger.debug(u"TARGET: {0}".format(target))

                try:
                    shutil.copyfile(source, target)  # Copy icon to TP Plugin folder
                except IOError as io_error:
                    self.logger.error(u"IO Error detected in Touch Portal Plugin [deviceStartComm of device '{0}']: {1}".format(dev.name, io_error))

            # On device start - default to off state. Disabled devices will be skipped.
            dev.updateStateOnServer("onOffState", False, uiValue="Disconnected", clearErrorState=True)
            indigo.devices[dev].updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
            dev.updateStateOnServer("connection_status", "Disconnected")

            self.globals[K_TP][dev_id][K_MONITORED_DEVICES] = {}  # Dictionary will be filled by entry_tp_generator

            # Write out a new entry.tp file to the TP desktop machine.
            entry_tp_created = entry_tp_generator.construct(self, dev_id)
            if not entry_tp_created:
                self.logger.warning(
                    u"unable to create/update TP Desktop's Indigo plugin file for Indigo Touch Portal device '{0}'"
                    " - Maybe you haven't created any Touch Portal items yet?"
                    .format(dev.name))
                return  # Can't start device

            auto_connect = bool(dev.pluginProps.get("auto_connect", TP_AUTO_CONNECT_DEFAULT))

            if auto_connect:
                self.tp_connect(dev)

            self.globals[K_TP][dev_id][K_DEVICE_STARTED] = True

        except StandardError as standard_error_message:
            self.logger.error(u"StandardError detected in Touch Portal Plugin [deviceStartComm of device '{0}']. "
                              u"Line '{1}' has error='{2}'".format(dev.name,
                                                                   sys.exc_traceback.tb_lineno,
                                                                   standard_error_message))

    # =============================================================================
    def deviceStopComm(self, dev):
        """
        Indigo method invoked when plugin device is stopped.

        -----
        :param dev:
        :return:
        """

        dev_id = dev.id

        dev.updateStateOnServer("onOffState", False, uiValue="Disconnected", clearErrorState=True)
        dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

        # Check if TP Reader thread is running for this Touch Portal device and if so, stop it
        if dev_id in self.globals[K_THREADS]:
            if K_THREAD_READER in self.globals[K_THREADS][dev_id]:
                try:
                    self.globals[K_THREADS][dev_id][K_THREAD_READER][K_EVENT].set()
                except StandardError as standard_error_message:
                    self.logger.error(u"Error detected in Touch Portal Plugin [deviceStopComm of device '{0}']. "
                                      u"Line '{1}' has error='{2}'".format(dev.name,
                                                                           sys.exc_traceback.tb_lineno,
                                                                           standard_error_message))

        # Check if TP Handler thread is running for this Touch Portal device and if so, stop it
        if dev_id in self.globals[K_THREADS]:
            if K_THREAD_HANDLER in self.globals[K_THREADS][dev_id]:
                try:
                    self.globals[K_THREADS][dev_id][K_THREAD_HANDLER][K_EVENT].set()
                except StandardError as standard_error_message:
                    self.logger.error(u"Error detected in Touch Portal Plugin [deviceStopComm of device '{0}']. "
                                      u"Line '{1}' has error='{2}'".format(dev.name,
                                                                           sys.exc_traceback.tb_lineno,
                                                                           standard_error_message))

        if not self.globals[K_TP][dev_id][K_DEVICE_STARTED]:
            self.logger.debug(u"Touch Portal: '{0}' device stopping but startup not yet completed".format(dev.name))

        self.globals[K_TP][dev_id][K_DEVICE_STARTED] = False

        self.logger.info(u"Stopped '{0}' device".format(dev.name))

    # =============================================================================
    def deviceUpdated(self, orig_dev, new_dev):
        """
        Indigo method invoked when any Indigo device is changed.

        -----
        :param orig_dev:
        :param new_dev:
        :return:
        """

        try:
            if new_dev.deviceTypeId == 'touchPortal':  # Ignore Touch Portal device updates!
                return

            # Debug logging
            # self.logger.error(
            #     u"deviceUpdated '{0}, 'K_MONITORED_DEVICES': {1}"
            #     .format(new_dev.name, self.globals[K_TP][K_MONITORED_DEVICES]))

            # At this point check if device is known to Touch Portal desktop
            # and if so update required states if they have changed.

            if K_MONITORED_DEVICES in self.globals[K_TP]:
                if new_dev.id in self.globals[K_TP][K_MONITORED_DEVICES]:
                    monitor_list = self.globals[K_TP][K_MONITORED_DEVICES][new_dev.id]
                    tp_desktop_device_id = monitor_list[TP_MONITOR_TP_DESKTOP_DEV_ID]
                    tp_state_id = monitor_list[TP_MONITOR_TP_STATE_ID]
                    monitor_on_off = monitor_list[TP_MONITOR_ON_OFF]
                    monitor_brightness = monitor_list[TP_MONITOR_BRIGHTNESS]
                    monitor_rgb = monitor_list[TP_MONITOR_RGB]

                    if monitor_on_off:
                        if orig_dev.onState != new_dev.onState:
                            self.logger.debug(
                                u"K_MONITORED_DEVICE [ON_OFF]:\n{0}\n".format(self.globals[K_TP][K_MONITORED_DEVICES]))
                            new_state_value = "OFF"
                            if new_dev.onState:
                                new_state_value = "ON"
                            tp_state_id = u"indigo_device_{0}_on_off".format(new_dev.id)
                            tp_message = '{{"type": "stateUpdate", "id": "{0}", "value" : "{1}"}}'.format(
                                tp_state_id, new_state_value)
                            self.globals[K_THREADS][tp_desktop_device_id][K_THREAD_HANDLER][K_THREAD].process_send_tp_message(tp_desktop_device_id, tp_message)

                    if monitor_brightness:
                        if orig_dev.brightness != new_dev.brightness:
                            self.logger.debug(
                                u"K_MONITORED_DEVICE [BRIGHTNESS]:\n{0}\n".format(self.globals[K_TP][K_MONITORED_DEVICES]))
                            new_state_value = new_dev.brightness
                            tp_state_id = u"indigo_device_{0}_brightness".format(new_dev.id)
                            tp_message = '{{"type": "stateUpdate", "id": "{0}", "value" : "{1}"}}'.format(
                                tp_state_id, new_state_value)
                            self.globals[K_THREADS][tp_desktop_device_id][K_THREAD_HANDLER][K_THREAD].process_send_tp_message(tp_desktop_device_id, tp_message)

                    if monitor_rgb:
                        if orig_dev.redLevel != new_dev.redLevel or orig_dev.greenLevel != new_dev.greenLevel or orig_dev.blueLevel != new_dev.blueLevel:
                            self.logger.debug(
                                u"K_MONITORED_DEVICE [COLOUR RGB]:\n{0}\n".format(self.globals[K_TP][K_MONITORED_DEVICES]))
                            red_level = int((new_dev.redLevel * 255.0) / 100.0)
                            green_level = int((new_dev.greenLevel * 255.0) / 100.0)
                            blue_level = int((new_dev.blueLevel * 255.0) / 100.0)
                            new_state_value = ('#FF%02x%02x%02x' % (red_level, green_level, blue_level)).upper()
                            tp_state_id = u"indigo_device_{0}_colour_rgb".format(new_dev.id)
                            tp_message = '{{"type": "stateUpdate", "id": "{0}", "value" : "{1}"}}'.format(
                                tp_state_id, new_state_value)
                            self.globals[K_THREADS][tp_desktop_device_id][K_THREAD_HANDLER][K_THREAD].process_send_tp_message(tp_desktop_device_id, tp_message)

        except StandardError as standard_error_message:
            self.logger.error(u"StandardError detected in Touch Portal Plugin [deviceUpdated] for device '{0}']. "
                              u"Line '{1}' has error='{2}'".format(new_dev.name,
                                                                   sys.exc_traceback.tb_lineno,
                                                                   standard_error_message))

        finally:
            indigo.PluginBase.deviceUpdated(self, orig_dev, new_dev)

    # =============================================================================
    def didDeviceCommPropertyChange(self, orig_dev, new_dev):
        """
        Indigo method invoked when a plugin device is changed to check whether
        properties Host/Port/Timeout property have changed. If so, a device start is
        required otherwise not A change to other properties won't force a restart

        -----
        :param orig_dev:
        :param new_dev:
        :return:
        """

        try:
            orig_host = orig_dev.pluginProps.get("host", TP_HOST_DEFAULT)
            new_host = new_dev.pluginProps.get("host", TP_HOST_DEFAULT)
            if orig_host != new_host:
                return True

            orig_port = orig_dev.pluginProps.get("port", TP_PORT_DEFAULT)
            new_port = new_dev.pluginProps.get("port", TP_PORT_DEFAULT)
            if orig_port != new_port:
                return True

            orig_timeout = orig_dev.pluginProps.get("timeout", TP_SOCKET_TIMEOUT_DEFAULT)
            new_timeout = new_dev.pluginProps.get("timeout", TP_SOCKET_TIMEOUT_DEFAULT)
            if orig_timeout != new_timeout:
                return True

            orig_tp_user_data_folder_path = orig_dev.pluginProps.get("tp_user_data_folder_path", TP_DESKTOP_USER_DATA_FOLDER_DEFAULT_PATH)
            new_tp_user_data_folder_path = new_dev.pluginProps.get("tp_user_data_folder_path", TP_DESKTOP_USER_DATA_FOLDER_DEFAULT_PATH)
            if orig_tp_user_data_folder_path != new_tp_user_data_folder_path:
                return True

            orig_tp_devices_last_updated_date_time = orig_dev.pluginProps.get("tp_devices_last_updated_date_time", None)
            new_tp_devices_last_updated_date_time = new_dev.pluginProps.get("tp_devices_last_updated_date_time", None)
            # self.logger.debug(u"UPDATED TIME: OLD = {0}, NEW = {1}".format(orig_tp_devices_last_updated_date_time, new_tp_devices_last_updated_date_time))
            if orig_tp_devices_last_updated_date_time != new_tp_devices_last_updated_date_time:
                return True

            return False

        except StandardError as standard_error_message:
            self.logger.error(u"StandardError detected in Touch Portal Plugin [didDeviceCommPropertyChange] for device "
                              u"'{0}']. Line '{1}' has error='{2}'".format(new_dev.name,
                                                                           sys.exc_traceback.tb_lineno,
                                                                           standard_error_message))

    # =============================================================================
    def getDeviceConfigUiValues(self, plugin_props, type_id, dev_id):
        """
        Indigo method called to pre-populate device config dialogs.

        -----
        :param plugin_props:
        :param type_id:
        :param dev_id:
        :return:
        """

        try:
            if "host" not in plugin_props:
                plugin_props["host"] = plugin_props.get("host", TP_HOST_DEFAULT)  # Address of Touch Portal Desktop

            if "port" not in plugin_props:
                plugin_props["port"] = TP_PORT_DEFAULT  # Touch Portal desktop plugin listening port

            plugin_props["timeout"] = TP_SOCKET_TIMEOUT_DEFAULT  # Force timeout to plugin default number of seconds

            if "tp_user_data_folder_path" not in plugin_props:
                plugin_props["tp_user_data_folder_path"] = u"{0}{1}".format(os.path.expanduser("~"),
                                                                            TP_DESKTOP_USER_DATA_FOLDER_DEFAULT_PATH)

            if "auto_connect" not in plugin_props:
                plugin_props["auto_connect"] = bool(TP_AUTO_CONNECT_DEFAULT)  # Auto connect?

            if "show_variable_value" not in plugin_props:
                plugin_props["show_variable_value"] = bool(TP_SHOW_VARIABLE_VALUE_DEFAULT)  # Show Variable Messages?

            if "socket_retry_seconds" not in plugin_props:
                plugin_props["socket_retry_seconds"] = TP_SOCKET_RETRY_DEFAULT  # Socket error retry every n seconds?

            if "socket_retry_silent_after" not in plugin_props:
                plugin_props["socket_retry_silent_after"] = TP_SOCKET_RETRY_SILENT_AFTER_DEFAULT  # Socket error retry silent after n attempts?

            if "tp_devices" not in plugin_props or plugin_props["tp_devices"] == "":
                plugin_props["tp_devices"] = json.dumps({})  # Empty dictionary in JSON container

            # TEMPORARY CODE - To tidy up pluginProps
            if "autoConnect" in plugin_props:
                del plugin_props["autoConnect"]
            if "hideMessages" in plugin_props:
                del plugin_props["hideMessages"]
            if "showVariableValue" in plugin_props:
                del plugin_props["showVariableValue"]
            if "socketRetrySeconds" in plugin_props:
                del plugin_props["socketRetrySeconds"]
            if "socketRetrySilentAfter" in plugin_props:
                del plugin_props["socketRetrySilentAfter"]
            if "entry_tp_location" in plugin_props:
                del plugin_props["entry_tp_location"]

            # Initialise the fields related to managing Touch Portal items
            self.initialise_device_config_dialogue(plugin_props)

            # Save initial values prior to any changes
            self.save_initial_device_config_values(plugin_props, dev_id)

        except StandardError as standard_error_message:
            self.logger.error(u"StandardError detected in Touch Portal Plugin [validateSchedule] for device '{0}'. "
                              u"Line '{1}' has error='{2}'".format(indigo.devices[dev_id].name,
                                                                   sys.exc_traceback.tb_lineno,
                                                                   standard_error_message))

        return super(Plugin, self).getDeviceConfigUiValues(plugin_props, type_id, dev_id)

    # =============================================================================
    def getPrefsConfigUiValues(self):
        """
        Indigo method called to pre-populate plugin config dialog.
        """

        prefs_config_ui_values = self.pluginPrefs

        return prefs_config_ui_values

    # =============================================================================
    def runConcurrentThread(self):

        try:
            while True:
                self.sleep(5)  # Sleep for 5 seconds

                if self.globals[K_RECOVERY_INVOKED]:
                    if len(self.globals[K_RECOVERY_INVOKED]) > 0:

                        # Initiate socket recovery process - See method handleCommunication in tpReader
                        self.globals[K_LOCK].acquire()  # Serialise update of 'recoveryInvoked' list
                        dev_id = self.globals[K_RECOVERY_INVOKED].pop(0)  # retrieve first (likely only) device to recover
                        self.globals[K_LOCK].release()

                        dev = indigo.devices[dev_id]
                        connected = self.tp_connect(dev)
                        if connected:
                            self.logger.debug(u"\"{0}\" attempting reconnection to the Touch Portal Desktop".format(dev.name))
                        else:
                            self.logger.error(u"\"{0}\" reconnecting to the Touch Portal Desktop failed".format(dev.name))

        except self.StopThread:
            pass    # Optionally catch the StopThread exception and do any needed cleanup.

    # =============================================================================
    def shutdown(self):
        """
        Indigo method invoked when plugin shutdown command is called.

        """

        self.logger.debug(u"Shutdown called")
        self.logger.info(u"'Touch Portal' Plugin shutdown complete")

    # =============================================================================
    def startup(self):
        """
        Indigo method invoked when plugin is enabled.
        """

        indigo.devices.subscribeToChanges()
        indigo.variables.subscribeToChanges()
        self.logger.debug(u"Touch Portal initialisation complete")

    # =============================================================================
    def stopConcurrentThread(self):
        """
        Indigo method invoked after plugin shutdown command is processed.
        """

        self.logger.debug(u"Thread shutdown called")
        self.stopThread = True

    # =============================================================================
    def validateActionConfigUi(self, values_dict, type_id, action_id):
        """
        Indigo validation method invoked when action config dialog is closed.

        -----
        :param values_dict:
        :param type_id:
        :param action_id:
        :return:
        """

        try:
            self.logger.debug(u"Validate Action Config UI: typeId = '{0}', actionId = '{1}', "
                              u"values_dict =\n{2}\n".format(type_id, action_id, values_dict))

            error_dict = indigo.Dict()

            if type_id == "update_tp_custom_state_bool" or type_id == "update_tp_custom_state_text":

                # =============================== Custom State Field ===============================
                if values_dict["update_custom_state_id"] == "_SELECT":
                    error_dict["update_custom_state_id"] = u"You must select a Custom State."

            # ============================ Process Any Errors =============================
            if len(error_dict) > 0:
                return False, values_dict, error_dict
            else:
                return True, values_dict

        except StandardError as standard_error_message:
            self.logger.error(u"StandardError detected in Touch Portal Plugin [validateActionConfigUi]. "
                              u"Line '{0}' has error='{1}'".format(indigo.devices[action_id].name,
                                                                   sys.exc_traceback.tb_lineno,
                                                                   standard_error_message))

    # =============================================================================
    def validateDeviceConfigUi(self, values_dict, type_id, dev_id):  # Validate Touch PortalThermostat Controller
        """
        Indigo validation method invoked when device config dialog is closed.

        -----

        :param values_dict:
        :param type_id:
        :param dev_id:
        :return:
        """

        try:
            error_dict = indigo.Dict()

            # =============================== Host IP Field ===============================
            try:
                host_len = len(values_dict["host"].split("."))
                if host_len < 4:
                    raise ValueError
            except ValueError:
                error_dict["host"] = u"The host IP must be a valid IP."

            # ================================ Port Field =================================
            try:
                int(values_dict["port"])   # Throws a ValueError if not numeric
                if values_dict["port"] <= 0:
                    error_dict["port"] = u"The port value must be greater than zero."
            except ValueError:
                error_dict["port"] = u"The port value must be a numeric value."

            # =============================== Timeout Field ===============================
            try:
                int(values_dict["timeout"])   # Throws a ValueError if not numeric
                if values_dict["timeout"] < 1:
                    error_dict["timeout"] = u"The socket timeout value cannot be less than 1."
            except ValueError:
                error_dict["timeout"] = u"The socket timeout value must be a numeric value."

            # =============================== Socket Retry Seconds Field ===============================
            try:
                int(values_dict["socket_retry_seconds"])   # Throws a ValueError if not numeric
                if values_dict["socket_retry_seconds"] < 10:
                    error_dict["socket_retry_seconds"] = u"The socket retry after n seconds value cannot be less than 10."
            except ValueError:
                error_dict["socket_retry_seconds"] = u"The socket retry after n seconds value must be a numeric value."

            # =============================== Socket Retry Silent After Field ===============================
            try:
                int(values_dict["socket_retry_silent_after"])   # Throws a ValueError if not numeric
                if values_dict["socket_retry_silent_after"] < 0:
                    error_dict["socket_retry_silent_after"] = u"The retry silent after n attempts value can't be less than zero."
            except ValueError:
                error_dict["socket_retry_silent_after"] = u"The retry silent after 'n' attempts value must be a numeric value."

            # =============================== Save button "safety net' ===============================
            error_button = ""
            if values_dict["tp_devices_list"] == "_ADD":
                if values_dict["new_tp_device_name"] != "":
                    error_dict["new_tp_device_name"] = u"Item name not empty"
                    error_button = "Add New"
            else:
                if values_dict["updated_tp_device_name"] != "":
                    error_dict["updated_tp_device_name"] = u"Item name not empty"
                    error_button = "Update"
            if error_button != "":
                error_dict["showAlertText"] = (u"The Item Name is not empty."
                                               u" Have you saved your item by clicking the"
                                               u" '{0} Touch Portal Item' button below?"
                                               u" Clear the Item Name field to enable Save."
                                               .format(error_button))

            # ============================ Process Any Errors =============================
            if len(error_dict) > 0:
                return False, values_dict, error_dict
            else:
                return True, values_dict

        except StandardError as standard_error_message:
            self.logger.error(u"StandardError detected in [validateDeviceConfigUi] for device '{0}'"
                              ". Line {1} has error='{2}'"
                              .format(indigo.devices[dev_id].name, sys.exc_traceback.tb_lineno, standard_error_message))

    # =============================================================================
    def validatePrefsConfigUi(self, values_dict):
        """
        Indigo validation method invoked when plugin config dialog is closed.

        -----
        :param values_dict:
        :return:
        """

        return True

        # =============================================================================

    # =============================================================================
    def variableUpdated(self, orig_var, new_var):
        """
        Indigo method invoked when any Indigo variable is changed.

        -----
        :param orig_var:
        :param new_var:
        :return:
        """

        try:
            # At this point check if variable is known to Touch Portal desktop
            # and if so update required states if they have changed.

            if K_MONITORED_VARIABLES in self.globals[K_TP]:
                if new_var.id in self.globals[K_TP][K_MONITORED_VARIABLES]:
                    monitor_list = self.globals[K_TP][K_MONITORED_VARIABLES][new_var.id]
                    tp_desktop_device_id = monitor_list[TP_MONITOR_TP_DESKTOP_DEV_ID]
                    tp_state_id = monitor_list[TP_MONITOR_TP_STATE_ID]
                    monitor_true_false = monitor_list[TP_MONITOR_TRUE_FALSE]
                    monitor_text = monitor_list[TP_MONITOR_TEXT]

                    if monitor_true_false:
                        if orig_var.value != new_var.value:
                            self.logger.debug(
                                u"K_MONITORED_VARIABLE [ON_OFF]:\n{0}\n".format(self.globals[K_TP][K_MONITORED_VARIABLES]))

                            new_state_value = new_var.value.lower()
                            if new_state_value == "false" or new_state_value == "true":
                                tp_state_id = u"indigo_variable_{0}_true_false".format(new_var.id)
                                tp_message = '{{"type": "stateUpdate", "id": "{0}", "value" : "{1}"}}'.format(tp_state_id, new_state_value)

                                self.globals[K_THREADS][tp_desktop_device_id][K_THREAD_HANDLER][K_THREAD].process_send_tp_message(tp_desktop_device_id, tp_message)
                            else:
                                self.logger.error(u"Touch Portal monitored boolean Variable '{0}' update "
                                                  u"intercepted to non-bool value: '{1}' - State Update "
                                                  u"ignored!".format(new_var.name, new_state_value))

                    elif monitor_text:
                        if orig_var.value != new_var.value:
                            self.logger.debug(
                                u"K_MONITORED_VARIABLE [TEXT]:\n{0}\n".format(self.globals[K_TP][K_MONITORED_VARIABLES]))

                            tp_state_id = u"indigo_variable_{0}_true_false".format(new_var.id)
                            tp_message = '{{"type": "stateUpdate", "id": "{0}", "value" : "{1}"}}'.format(tp_state_id, new_var.value)

                            self.globals[K_THREADS][tp_desktop_device_id][K_THREAD_HANDLER][K_THREAD].process_send_tp_message(tp_desktop_device_id, tp_message)

        except StandardError as standard_error_message:
            self.logger.error(u"StandardError detected in Touch Portal Plugin [variableUpdated] for variable '{0}']. "
                              u"Line '{1}' has error='{2}'".format(new_var.name,
                                                                   sys.exc_traceback.tb_lineno,
                                                                   standard_error_message))

    # =============================================================================
    def action_device_variable_selection(self, values_dict, typeId, ahbDevId):
        if values_dict["action_device_variable_selection"] == "A" or \
                values_dict["action_device_variable_selection"] == "V":
            values_dict["source_device_supports_on_off_state"] = False
            values_dict["source_device_supports_brightness_state"] = False
            values_dict["source_device_supports_colourRGB_state"] = False
        if values_dict["action_device_variable_selection"] == "A":
            values_dict["source_action_group_menu"] = 0
        elif values_dict["action_device_variable_selection"] == "D":
            values_dict["source_device_menu"] = 0
        elif values_dict["action_device_variable_selection"] == "V":
            values_dict["source_variable_menu"] = 0

        return values_dict

    # =============================================================================
    def action_groups_to_list(self, filter="", values_dict=None, typeId="", targetId=0):
        # Set a default with id 0
        # Iterates through the action list

        action_group_list = [(0, "-- Select Action Group --")]
        for action_group in indigo.actionGroups:
            action_group_list.append((action_group.id, action_group.name))
        return action_group_list

    # =============================================================================
    def action_refresh_tp_plugin_states(self, action):
        """
        Indigo action method invoked to refresh all Touch Portal Plugin States (see Actions.xml).

        -----
        :param action:
        :return:
        """
        dev_id = action.deviceId

        try:
            self.globals[K_QUEUES][dev_id][K_RECEIVE_FROM_SEND_TO_TP]\
                .put([QUEUE_PRIORITY_HIGH, 0, CMD_PROCESS_REFRESH_TP_PLUGIN_STATES, dev_id, None])

        except StandardError as standard_error_message:
            self.logger.error(u"StandardError detected in Touch Portal Plugin [action_refresh_tp_plugin_states] for "
                              u"device '{0}'. Line '{1}' has error='{2}'".format(indigo.devices[dev_id].name,
                                                                                 sys.exc_traceback.tb_lineno,
                                                                                 standard_error_message))

    # =============================================================================
    def action_tp_custom_States_list(self, filter, values_dict, typeId, dev_id):
        """
        Indigo action method invoked to return a list of TP Custom States (see Actions.xml).

        -----
        :param filter:
        :param values_dict:
        :param typeId:
        :param dev_id:
        :return:
        """
        try:
            dev = indigo.devices[dev_id]
            states_file = u"{0}/states.tp".format(dev.ownerProps['tp_user_data_folder_path'])

            with open(states_file, "r") as read_file:
                custom_states = json.load(read_file)

            custom_states_list = []
            for custom_state_info in custom_states:
                state_id = custom_state_info["STATE_ID"]
                state_name = custom_state_info["STATE_PRETTY_NAME"]
                custom_states_list.append([state_id, state_name])

            custom_states_list = sorted(custom_states_list, key=lambda item: item[1])  # Sort list by Pretty Name
            custom_states_list.insert(0, ["_SELECT", "- Select Custom State -"])  # Insert at start of sorted list

            return custom_states_list

        except StandardError as standard_error_message:
            self.logger.error(u"StandardError detected in Touch Portal Plugin [action_refresh_tp_plugin_states] "
                              u"for device '{0}'. Line '{1}' has error='{2}'".format(indigo.devices[dev_id].name,
                                                                                     sys.exc_traceback.tb_lineno,
                                                                                     standard_error_message))

    # =============================================================================
    def action_update_tp_custom_state(self, action):
        """
        Indigo action method invoked to update a Touch Portal Custom State (see Actions.xml).

        -----
        :param action:
        :return:
        """

        dev_id = action.deviceId
        dev = indigo.devices[dev_id]
        try:
            tp_id = action.props.get("update_custom_state_id")

            custom_state_found = False

            states_file = u"{0}/states.tp".format(dev.ownerProps['tp_user_data_folder_path'])
            with open(states_file, "r") as read_file:
                custom_states = json.load(read_file)
            for custom_state_info in custom_states:
                if custom_state_info["STATE_ID"] == tp_id:
                    custom_state_found = True
                    break

            if not custom_state_found:
                self.logger.error(u"Custom State '{0}' not defined in Touch Portal Desktop - update ignored"
                                  .format(tp_id))
                return

            tp_value = action.props.get("update_state_value", "")
            self.logger.debug(u"UPDATESTATEVALUE [{0}] = {1}".format(type(tp_value), tp_value))

            if tp_value != "":
                #  Only send value if not blank -
                state_update_message = ('{{"type":"{0}","id":"{1}","value":"{2}"}}'
                                        .format("stateUpdate", tp_id, tp_value))

                self.logger.debug(u"STATE_UPDATE_MESSAGE = {0}".format(state_update_message))

                # self.globals[K_QUEUES][dev_id][K_SEND_TO_TP].put([QUEUE_PRIORITY_HIGH, 0, CMD_PROCESS_SEND_TP_MESSAGE, dev_id, [state_update_message]])

                self.globals[K_THREADS][dev_id][K_THREAD_HANDLER][K_THREAD].process_send_tp_message(dev_id, state_update_message)

            else:
                self.logger.error(u"STATE_UPDATE_MESSAGE: Value missing for device "
                                  u"{0}".format(indigo.devices[dev_id].name))

        except StandardError as standard_error_message:
            self.logger.error(u"StandardError detected in Touch Portal Plugin [actionUpdateStateTest for device "
                              u"'{0}']. Line '{1}' has error='{2}'".format(indigo.devices[dev_id].name,
                                                                           sys.exc_traceback.tb_lineno,
                                                                           standard_error_message))

    # =============================================================================
    def add_new_tp_device(self, values_dict, type_id, dev_id):

        if values_dict["new_tp_device_name"] == "":
            error_dict = indigo.Dict()
            error_dict["new_tp_device_name"] = u"New Touch Portal item name is missing and must be present."
            error_dict["showAlertText"] = u"New Touch Portal item name is missing and must be present."
            return values_dict, error_dict

        if '|' in values_dict["new_tp_device_name"]:
            error_dict = indigo.Dict()
            error_dict["new_tp_device_name"] = u"New Touch Portal item name cannot contain a vertical bar (i.e. '|')"
            error_dict["showAlertText"] = u"New Touch Portal item name cannot contain a vertical bar (i.e. '|')"
            return values_dict, error_dict

        if ',' in values_dict["new_tp_device_name"]:
            error_dict = indigo.Dict()
            error_dict["new_tp_device_name"] = u"New Touch Portal item name cannot contain a comma."
            error_dict["showAlertText"] = u"New Touch Portal item name cannot contain a comma."
            return values_dict, error_dict

        if ';' in values_dict["new_tp_device_name"]:
            error_dict = indigo.Dict()
            error_dict["new_tp_device_name"] = u"New Touch Portal item name cannot contain a semicolon."
            error_dict["showAlertText"] = u"New Touch Portal Name item name contain a semicolon."
            return values_dict, error_dict

        new_tp_device_name = values_dict["new_tp_device_name"]
        new_tp_device_name_key = new_tp_device_name.lower()

        if values_dict["action_device_variable_selection"] == 'D':
            indigo_dev_id = int(values_dict["source_device_menu"])
            if indigo_dev_id == 0:
                error_dict = indigo.Dict()
                error_dict["source_device_menu"] = u"Indigo Device not selected"
                error_dict["showAlertText"] = u"No Indigo Device selected for Touch Portal item: '{0}'".format(new_tp_device_name)
                return values_dict, error_dict
        elif values_dict["action_device_variable_selection"] == 'A':
            indigo_action_group_id = int(values_dict["source_action_group_menu"])
            if indigo_action_group_id == 0:
                error_dict = indigo.Dict()
                error_dict["source_action_group_menu"] = u"Indigo Action Group not selected"
                error_dict["showAlertText"] = u"No Indigo Action Group selected for Touch Portal item: '{0}'".format(new_tp_device_name)
                return values_dict, error_dict
        elif values_dict["action_device_variable_selection"] == 'V':
            indigo_variable_id = int(values_dict["source_variable_menu"])
            if indigo_variable_id == 0:
                error_dict = indigo.Dict()
                error_dict["source_variable_menu"] = u"Indigo variable not selected"
                error_dict["showAlertText"] = u"No Indigo variable selected for Touch Portal item: '{0}'".format(new_tp_device_name)
                return values_dict, error_dict
        else:
            error_dict = indigo.Dict()
            error_dict["action_device_variable_selection"] = u"Indigo Action / Device / Variable menu option not selected"
            error_dict["showAlertText"] = u"Indigo Action / Device / Variable menu option not selected for " \
                                          u"Touch Portal Device: '{0}'".format(new_tp_device_name)
            return values_dict, error_dict

        try:
            if "tp_devices" not in values_dict:
                values_dict["tp_devices"] = json.dumps({})  # Empty dictionary in JSON container
            tp_devices = json.loads(values_dict["tp_devices"])

            for tp_name_key, tp_data in tp_devices.iteritems():
                if new_tp_device_name_key == tp_name_key:
                    error_dict = indigo.Dict()
                    error_dict["new_tp_device_name"] = "Duplicate Touch Portal item name"
                    error_dict["showAlertText"] = u"Touch Portal Device Name '{0}' is already allocated.".format(
                        new_tp_device_name)
                    return values_dict, error_dict

            tp_devices[new_tp_device_name_key] = {}
            tp_devices[new_tp_device_name_key]["tp_name"] = new_tp_device_name

            if values_dict["action_device_variable_selection"] == 'D':
                indigo_dev_id = int(values_dict["source_device_menu"])
                indigo_dev = indigo.devices[indigo_dev_id]
                tp_devices[new_tp_device_name_key]["mode"] = 'D'
                tp_devices[new_tp_device_name_key]["dev_id"] = indigo_dev_id
                tp_devices[new_tp_device_name_key]["dev_name"] = indigo_dev.name
                tp_devices[new_tp_device_name_key]["dev_dim_action"] = bool(values_dict["source_device_dim_action"])

                if "onOffState" in indigo_dev.states:
                    tp_devices[new_tp_device_name_key]["supports_on_off_state"] = True
                    tp_devices[new_tp_device_name_key]["create_tp_on_off_state"] = bool(values_dict["create_tp_on_off_state"])
                else:
                    tp_devices[new_tp_device_name_key]["supports_on_off_state"] = False

                if "brightnessLevel" in indigo_dev.states:
                    tp_devices[new_tp_device_name_key]["supports_brightness_state"] = True
                    tp_devices[new_tp_device_name_key]["create_tp_brightness_state"] = bool(values_dict["create_tp_brightness_state"])
                else:
                    tp_devices[new_tp_device_name_key]["supports_brightness_state"] = False

                if not hasattr(indigo_dev, "supportsRGB")\
                        or not hasattr(indigo_dev, "supportsColor")\
                        or not indigo_dev.supportsRGB\
                        or not indigo_dev.supportsColor:  # Check device supports color
                    tp_devices[new_tp_device_name_key]["supports_colourRGB_state"] = False
                else:
                    tp_devices[new_tp_device_name_key]["supports_colourRGB_state"] = True
                    tp_devices[new_tp_device_name_key]["create_tp_colourRGB_state"] = bool(values_dict["create_tp_colourRGB_state"])

            elif values_dict["action_device_variable_selection"] == "A":
                indigo_action_group_id = int(values_dict["source_action_group_menu"])
                tp_devices[new_tp_device_name_key]["mode"] = "A"
                tp_devices[new_tp_device_name_key]['action_group_id'] = indigo_action_group_id

            elif values_dict["action_device_variable_selection"] == 'V':
                indigo_variable_id = int(values_dict["source_variable_menu"])
                tp_devices[new_tp_device_name_key]["mode"] = "V"
                tp_devices[new_tp_device_name_key]['variable_id'] = indigo_variable_id

                variable = indigo.variables[indigo_variable_id]
                if variable.readOnly:
                    variable_value = variable.value.lower()

                    # As you can't modify a Read Only Variable, automatically force a TP plugin state to be created
                    if variable_value == "false" or variable_value == "true":
                        values_dict["variable_state_type"] = "B"
                        tp_devices[new_tp_device_name_key]["variable_state_type"] = values_dict["variable_state_type"]
                        tp_devices[new_tp_device_name_key]["supports_variable_tp_true_false_state"] = True
                        tp_devices[new_tp_device_name_key]["supports_variable_tp_text_state"] = False
                        tp_devices[new_tp_device_name_key]["create_variable_tp_true_false_state"] = True
                        tp_devices[new_tp_device_name_key]["create_variable_tp_text_state"] = False
                    else:
                        values_dict["variable_state_type"] = "T"
                        tp_devices[new_tp_device_name_key]["variable_state_type"] = values_dict["variable_state_type"]
                        tp_devices[new_tp_device_name_key]["supports_variable_tp_true_false_state"] = False
                        tp_devices[new_tp_device_name_key]["supports_variable_tp_text_state"] = True
                        tp_devices[new_tp_device_name_key]["create_variable_tp_true_false_state"] = False
                        tp_devices[new_tp_device_name_key]["create_variable_tp_text_state"] = True
                else:
                    # Not a 'Read Only' Variable
                    tp_devices[new_tp_device_name_key]["supports_variable_tp_true_false_state"] = False
                    tp_devices[new_tp_device_name_key]["supports_variable_tp_text_state"] = True
                    tp_devices[new_tp_device_name_key]["variable_state_type"] = "N"
                    if "variable_state_type" in values_dict:
                        tp_devices[new_tp_device_name_key]["variable_state_type"] = values_dict["variable_state_type"]
                        if values_dict["variable_state_type"] == "B":
                            tp_devices[new_tp_device_name_key]["supports_variable_tp_text_state"] = False
                            tp_devices[new_tp_device_name_key]["create_variable_tp_text_state"] = False
                            tp_devices[new_tp_device_name_key]["supports_variable_tp_true_false_state"] = True
                            tp_devices[new_tp_device_name_key]["create_variable_tp_true_false_state"] = True
                        elif values_dict["variable_state_type"] == "T":
                            tp_devices[new_tp_device_name_key]["supports_variable_tp_true_false_state"] = False
                            tp_devices[new_tp_device_name_key]["create_variable_tp_true_false_state"] = False
                            tp_devices[new_tp_device_name_key]["supports_variable_tp_text_state"] = True
                            tp_devices[new_tp_device_name_key]["create_variable_tp_text_state"] = True

            values_dict["tp_devices"] = json.dumps(tp_devices)

            update_time = datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d %H:%M:%S.%f')
            values_dict["tp_devices_last_updated_date_time"] = update_time

            self.initialise_device_config_dialogue(values_dict)

        except StandardError as err:
            self.logger.error(u"StandardError detected in add_new_tp_device for '{0}'. "
                              u"Line '{1}' has error='{2}'".format(indigo.devices[dev_id].name,
                                                                   sys.exc_traceback.tb_lineno,
                                                                   err))

        # self.logger.debug(u"add_new_tp_device VALUES DICT = {0}".format(values_dict))
        return values_dict

    # =============================================================================
    def delete_devices(self, values_dict, type_id, dev_id):
        try:
            pass

            published_tp_devices = json.loads(values_dict["tp_devices"])

            delete_list = values_dict["published_tp_devices_list"]
            for item_to_delete_name in delete_list:
                delete_name = item_to_delete_name.split("|")[1]  # Remove leading "A|", "D|" or "V|"
                del published_tp_devices[delete_name]

            values_dict["tp_devices"] = json.dumps(published_tp_devices)

            update_time = datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d %H:%M:%S.%f')
            values_dict["tp_devices_last_updated_date_time"] = update_time

        except StandardError as err:
            self.logger.error(u"StandardError detected in delete_devices for "
                              u"'{0}'. Line '{1}' has error='{2}'".format(indigo.devices[dev_id].name,
                                                                          sys.exc_traceback.tb_lineno,
                                                                          err))

        # self.logger.debug(u"delete_devices: VALUES DICT = {0}".format(values_dict))
        return values_dict

    # =============================================================================
    def devices_with_on_state(self, filter="", values_dict=None, typeId="", targetId=0):
        # Set a default with id 0
        # Iterates through the device list and only add the device if it has an onState property
        # but don't include any Touch Portal devices!

        device_list = [(0, "-- Select Device --")]
        for dev in indigo.devices:
            if hasattr(dev, "onState") and (dev.deviceTypeId != TP_DEVICE_TYPEID):
                device_list.append((dev.id, dev.name))
        return device_list

    # =============================================================================
    def initialise_device_config_dialogue(self, dialogue_dict):
        try:

            dialogue_dict["tp_devices_list"] = "_ADD"
            dialogue_dict["new_tp_device"] = "NEW"
            dialogue_dict["new_tp_device_name"] = ""
            dialogue_dict["updated_tp_device_name"] = ""
            dialogue_dict["action_device_variable_selection"] = "D"
            dialogue_dict["source_device_menu"] = 0
            dialogue_dict["source_device_dim_action"] = False  # TODO: May not need this?
            dialogue_dict["source_device_supports_on_off_state"] = False
            dialogue_dict["create_tp_on_off_state"] = False
            dialogue_dict["source_device_supports_brightness_state"] = False
            dialogue_dict["create_tp_brightness_state"] = False
            dialogue_dict["source_device_supports_colourRGB_state"] = False
            dialogue_dict["create_tp_colourRGB_state"] = False
            dialogue_dict["source_action_group_menu"] = 0
            dialogue_dict["source_variable_menu"] = 0
            dialogue_dict["variable_state_type"] = "N"
            dialogue_dict["supports_variable_tp_true_false_state"] = False
            dialogue_dict["supports_variable_tp_text_state"] = False
            dialogue_dict["create_variable_tp_true_false_state"] = False
            dialogue_dict["create_variable_tp_text_state"] = False

        except StandardError as err:
            self.logger.error(u"StandardError detected in initialise_device_config_dialogue for "
                              u"'{0}'. Line '{1}' has error='{2}'".format(indigo.devices[dev_id].name,
                                                                          sys.exc_traceback.tb_lineno,
                                                                          err))

    # =============================================================================
    def process_turn_off(self, dev, toggle):
        """
        Plugin method to process device turn off commands.
        Initiated by Indigo User via Indigo UI.
        Will Disconnect Indigo device from Touch Portal Desktop App.

        -----
        :param dev:
        :param toggle:
        :return:
        """

        if not dev.onState:
            self.logger.info(u"'{0}' already disconnected from Touch Portal Desktop".format(dev.name))
            return

        disconnected = self.tp_disconnect(dev)  # Returns bool (true = disconnected, false = disconnection failed)
        if disconnected:
            if toggle:
                process_ui = "Toggle"
            else:
                process_ui = "Turn Off"
            self.logger.info(u"Sent \"{0}\" {1} - Now disconnected from Touch Portal Desktop".format(dev.name,
                                                                                                     process_ui))

    # =============================================================================
    def process_turn_on(self, dev, toggle):
        """
        Plugin method to process device turn on commands.
        Initiated by Indigo User via Indigo UI.
        Will Connect Indigo device to Touch Portal Desktop App.

        -----
        :param dev:
        :param toggle:
        :return:
        """

        if dev.onState and dev.errorState == "":
            self.logger.info(u"'{0}' already connected to Touch Portal Desktop".format(dev.name))
            return

        # Connection is attempted if Device is currently off or in an error state
        connecting = self.tp_connect(dev)
        if connecting:
            if toggle:
                process_ui = "Toggle"
            else:
                process_ui = "Turn On"

            self.logger.info(u"Sent \"{0}\"  {1} - connecting to Touch Portal Desktop".format(dev.name, process_ui))

    # =============================================================================
    def published_tp_devices_list(self, filter, values_dict, typeId, dev_id):

        list_of_published_tp_devices = list()

        if "tp_devices" in values_dict:
            tp_devices = json.loads(values_dict["tp_devices"])
            for tp_name_key, tp_data in tp_devices.iteritems():
                list_name = tp_data["tp_name"]
                if tp_data["mode"] == 'D':  # Device
                    if tp_data["dev_id"] in indigo.devices:
                        indigo_dev = indigo.devices[tp_data["dev_id"]]
                        if indigo_dev.name != list_name:
                            list_name += u" = {}".format(indigo_dev.name)
                    else:
                        list_name += " = MISSING!"
                    list_name = u"[d] {0}".format(list_name)

                elif tp_data["mode"] == 'A':  # Action
                    if tp_data["action_group_id"] in indigo.actionGroups:
                        action_group = indigo.actionGroups[tp_data["action_group_id"]]
                        if action_group.name != list_name:
                            list_name += u" = {}".format(action_group.name)
                    else:
                        list_name += " = MISSING!"
                    list_name = u"[a] {0}".format(list_name)

                elif tp_data["mode"] == 'V':  # Variable
                    if tp_data["variable_id"] in indigo.variables:
                        variable = indigo.variables[tp_data["variable_id"]]
                        if variable.name != list_name:
                            list_name += u" = {}".format(variable.name)
                    else:
                        list_name += " = MISSING!"
                    list_name = u"[v] {0}".format(list_name)
                else:
                    # This shouldn't happen, but if it does ignore it!
                    continue

                tp_sort_key = u"{0}|{1}".format(tp_data["mode"], tp_name_key)

                list_of_published_tp_devices.append((tp_sort_key, list_name))

        list_of_published_tp_devices = sorted(list_of_published_tp_devices, key=lambda item: item[0])

        return list_of_published_tp_devices

    # =============================================================================
    def save_initial_device_config_values(self, values_dict, dev_id):
        try:
            if dev_id not in self.globals[K_TP]:
                self.globals[K_TP][dev_id] = {}
            self.globals[K_TP][dev_id][K_INITIAL_DEVICE_CONFIG_VALUES] = values_dict

            # Suppressed debugging message
            # self.logger.error(u"INITIAL VALUES DICT for '{0}':\n{1}\n"
            #                   .format(dev.name, values_dict))

            self.globals[K_TP][dev_id][K_INITIAL_DEVICE_CONFIG_VALUES][K_AUTO_CONNECT] = values_dict["auto_connect"]
            self.globals[K_TP][dev_id][K_INITIAL_DEVICE_CONFIG_VALUES][K_HOST] = values_dict["host"]
            self.globals[K_TP][dev_id][K_INITIAL_DEVICE_CONFIG_VALUES][K_PORT] = values_dict["port"]
            self.globals[K_TP][dev_id][K_INITIAL_DEVICE_CONFIG_VALUES][K_SHOW_VARIABLE_VALUE] = values_dict["show_variable_value"]
            self.globals[K_TP][dev_id][K_INITIAL_DEVICE_CONFIG_VALUES][K_SOCKET_RETRY_SECONDS] = values_dict["socket_retry_seconds"]
            self.globals[K_TP][dev_id][K_INITIAL_DEVICE_CONFIG_VALUES][K_SOCKET_RETRY_SILENT_AFTER] = values_dict["socket_retry_silent_after"]
            self.globals[K_TP][dev_id][K_INITIAL_DEVICE_CONFIG_VALUES][K_TP_USER_DATA_FOLDER_PATH] = values_dict["tp_user_data_folder_path"]
            if "tp_devices" in values_dict:
                self.globals[K_TP][dev_id][K_INITIAL_DEVICE_CONFIG_VALUES][K_TP_DEVICES] = values_dict["tp_devices"]
            else:
                self.globals[K_TP][dev_id][K_INITIAL_DEVICE_CONFIG_VALUES][K_TP_DEVICES] = None

        except StandardError as standard_error_message:
            self.logger.error(u"StandardError detected in Touch Portal Plugin [save_initial_device_config_values] for "
                              u"device '{0}'. Line '{1}' has error='{2}'".format(indigo.devices[dev_id].name,
                                                                                 sys.exc_traceback.tb_lineno,
                                                                                 standard_error_message))

    # =============================================================================
    def select_action_to_add_update(self, values_dict, typeId, ahbDevId):

        values_dict["source_device_supports_on_off_state"] = False
        values_dict["source_device_supports_brightness_state"] = False
        values_dict["source_device_supports_colourRGB_state"] = False

        action_group_id = int(values_dict["source_action_group_menu"])
        if action_group_id != 0:
            action_group = indigo.actionGroups[int(action_group_id)]
            if values_dict["new_tp_device_name"] == "":
                values_dict["new_tp_device_name"] = action_group.name
            if values_dict["updated_tp_device_name"] == "":
                values_dict["updated_tp_device_name"] = action_group.name
        return values_dict

    # =============================================================================
    def select_device_to_add_update(self, values_dict, typeId, ahbDevId):

        dev_id = int(values_dict["source_device_menu"])
        if dev_id != 0:
            dev = indigo.devices[int(dev_id)]
            if values_dict["new_tp_device_name"] == "":
                values_dict["new_tp_device_name"] = dev.name
            if values_dict["updated_tp_device_name"] == "":
                values_dict["updated_tp_device_name"] = dev.name

            if "onOffState" in dev.states:
                values_dict["source_device_supports_on_off_state"] = True
            else:
                values_dict["source_device_supports_on_off_state"] = False

            if "brightnessLevel" in dev.states:
                values_dict["source_device_supports_brightness_state"] = True
            else:
                values_dict["source_device_supports_brightness_state"] = False

            if not hasattr(dev, "supportsRGB")\
                    or not hasattr(dev, "supportsColor")\
                    or not dev.supportsRGB\
                    or not dev.supportsColor:  # Check device supports color
                values_dict["source_device_supports_colourRGB_state"] = False
            else:
                values_dict["source_device_supports_colourRGB_state"] = True

        return values_dict

    # =============================================================================
    def select_variable_to_add_update(self, values_dict, typeId, ahbDevId):

        values_dict["source_device_supports_on_off_state"] = False
        values_dict["source_device_supports_brightness_state"] = False
        values_dict["source_device_supports_colourRGB_state"] = False

        variable_id = int(values_dict["source_variable_menu"])
        if variable_id != 0:
            variable = indigo.variables[int(variable_id)]
            if values_dict["new_tp_device_name"] == "":
                values_dict["new_tp_device_name"] = variable.name
            if values_dict["updated_tp_device_name"] == "":
                values_dict["updated_tp_device_name"] = variable.name

            values_dict["variable_state_type"] = "N"  # Default to No States on Variable Change
            if variable.readOnly:
                variable_value = variable.value.lower()

                # As you can't modify a Read Only Variable, automatically force a TP plugin state to be created
                if variable_value == "false" or variable_value == "true":
                    values_dict["variable_state_type"] = "B"
                else:
                    values_dict["variable_state_type"] = "T"

        return values_dict

    # =============================================================================
    def tp_connect(self, dev):
        """
        Plugin method to process connection to Touch Portal Desktop App.

        -----
        :param dev:
        :return: bool Connection Success / Fail
        """

        try:

            dev_id = dev.id

            connecting_status = ""  # Assume no bad connection state message

            dev.updateStateOnServer("onOffState", True, uiValue="Connecting . . .", clearErrorState=True)
            dev.updateStateImageOnServer(indigo.kStateImageSel.TimerOn)
            dev.updateStateOnServer("connection_status", connecting_status)

            # Check if TP Reader thread is running for this Touch Portal device and if so, stop it
            if dev_id in self.globals[K_THREADS]:
                if K_THREAD_READER in self.globals[K_THREADS][dev_id]:
                    try:
                        self.globals[K_THREADS][dev_id][K_THREAD_READER][K_EVENT].set()
                        self.globals[K_THREADS][dev_id][K_THREAD_READER][K_THREAD].join(timeout=10)  # Wait at least 'timeout' seconds for thread to end
                    except StandardError as standard_error_message:
                        self.logger.error(u"StandardError [1] detected in Touch Portal Plugin [tp_connect of device "
                                          u"'{0}']. Line '{1}' has error='{2}'".format(dev.name,
                                                                                       sys.exc_traceback.tb_lineno,
                                                                                       standard_error_message))
                        connecting_status = u"TP Reader Thread purge error: '{0}'".format(standard_error_message)  # Error clearing out previous TP Reader thread

            # Check if TP Handler thread is running for this Touch Portal device and if so, stop it
            if dev_id in self.globals[K_THREADS]:
                if K_THREAD_HANDLER in self.globals[K_THREADS][dev_id]:
                    try:
                        self.globals[K_THREADS][dev_id][K_THREAD_HANDLER][K_EVENT].set()
                        self.globals[K_THREADS][dev_id][K_THREAD_HANDLER][K_THREAD].join(timeout=10)  # Wait at least 'timeout' seconds for thread to end
                    except StandardError as standard_error_message:
                        self.logger.error(u"StandardError [1] detected in Touch Portal Plugin [tp_connect of device "
                                          u"'{0}']. Line '{1}' has error='{2}'".format(dev.name,
                                                                                       sys.exc_traceback.tb_lineno,
                                                                                       standard_error_message))
                        connecting_status = u"TP Handler Thread purge error: '{0}'".format(standard_error_message)  # Error clearing out previous TP Handler thread

            if connecting_status == "":
                # Create (or replace) TP handler 'receive from / send to Touch Portal' queue
                if dev_id not in self.globals[K_QUEUES]:
                    self.globals[K_QUEUES][dev_id] = {}
                # Used to queue tpReader / tpHandler commands to be received from / sent to the Touch Portal Desktop
                self.globals[K_QUEUES][dev_id][K_RECEIVE_FROM_SEND_TO_TP] = Queue.PriorityQueue()
                self.globals[K_QUEUES][dev_id][K_INITIALISED] = True

            if connecting_status == "":
                # Now start the TP Handler thread for this Touch Portal
                if dev_id not in self.globals[K_THREADS]:
                    self.globals[K_THREADS][dev_id] = {}
                if K_THREAD_READER not in self.globals[K_THREADS][dev_id]:
                    self.globals[K_THREADS][dev_id][K_THREAD_READER] = {}
                try:
                    self.globals[K_THREADS][dev_id][K_THREAD_READER][K_INITIALISED] = False  # Set to True by the tpReader thread
                    self.globals[K_THREADS][dev_id][K_THREAD_READER][K_EVENT] = threading.Event()
                    self.globals[K_THREADS][dev_id][K_THREAD_READER][K_THREAD] = ThreadTpReader(self.globals, self.globals[K_THREADS][dev_id][K_THREAD_READER][K_EVENT], dev_id)
                    self.globals[K_THREADS][dev_id][K_THREAD_READER][K_THREAD].setDaemon(True)  # Forces thread to close if plugin is reloaded
                    self.globals[K_THREADS][dev_id][K_THREAD_READER][K_THREAD].start()
                except StandardError as standard_error_message:
                    self.logger.error(u"StandardError [3] detected in Touch Portal Plugin [tp_connect of device "
                                      u"'{0}']. Line '{1}' has error='{2}'".format(dev.name,
                                                                                   sys.exc_traceback.tb_lineno,
                                                                                   standard_error_message))
                    connecting_status = u"TP Reader  create Thread error: '{0}'".format(standard_error_message)  # Error creating TP Reader thread

                # Now start the TP Handler thread for this Touch Portal
                if dev_id not in self.globals[K_THREADS]:
                    self.globals[K_THREADS][dev_id] = {}
                if K_THREAD_HANDLER not in self.globals[K_THREADS][dev_id]:
                    self.globals[K_THREADS][dev_id][K_THREAD_HANDLER] = {}
                try:
                    self.globals[K_THREADS][dev_id][K_THREAD_HANDLER][K_INITIALISED] = False  # Set to True by the tpHandler thread
                    self.globals[K_THREADS][dev_id][K_THREAD_HANDLER][K_EVENT] = threading.Event()
                    self.globals[K_THREADS][dev_id][K_THREAD_HANDLER][K_THREAD] = ThreadTpHandler(self.globals, self.globals[K_THREADS][dev_id][K_THREAD_HANDLER][K_EVENT], dev_id)
                    self.globals[K_THREADS][dev_id][K_THREAD_HANDLER][K_THREAD].setDaemon(True)  # Forces thread to close if plugin is reloaded
                    self.globals[K_THREADS][dev_id][K_THREAD_HANDLER][K_THREAD].start()
                except StandardError as standard_error_message:
                    self.logger.error(u"StandardError [3] detected in Touch Portal Plugin [tp_connect of device "
                                      u"'{0}']. Line '{1}' has error='{2}'".format(dev.name,
                                                                                   sys.exc_traceback.tb_lineno,
                                                                                   standard_error_message))
                    connecting_status = u"TP Handler  create Thread error: '{0}'".format(standard_error_message)  # Error creating  TP Handler thread

            if connecting_status != "":
                dev.setErrorStateOnServer("Connection Error")
                dev.updateStateOnServer("connection_status", connecting_status)
                return False  # Error detected

            return True  # All OK

        except StandardError as standard_error_message:
            self.logger.error(u"StandardError detected in Touch Portal Plugin [tp_connect of device "
                              u"'{0}']. Line '{1}' has error='{2}'".format(dev.name,
                                                                           sys.exc_traceback.tb_lineno,
                                                                           standard_error_message))
            return False

    # =============================================================================
    def tp_devices_list(self, filter, values_dict, typeId, dev_id):

        allocated_tp_devices_list = [("_ADD", "Add New Item")]

        if "tp_devices" in values_dict:
            published_tp_devices = json.loads(values_dict["tp_devices"])
            for tp_name_key, tp_data in published_tp_devices.iteritems():
                allocated_tp_devices_list.append((tp_name_key, tp_data["tp_name"]))

        allocated_tp_devices_list = sorted(allocated_tp_devices_list, key=lambda item: item[0])

        return allocated_tp_devices_list

    # =============================================================================
    def tp_devices_list_selection(self, values_dict, typeId, ahbDevId):

        if "tp_devices_list" in values_dict:
            tp_name_selected = values_dict["tp_devices_list"]
            if tp_name_selected == "_ADD":
                self.initialise_device_config_dialogue(values_dict)
            else:
                values_dict["new_tp_device"] = 'EXISTING'
                if "tp_devices" in values_dict:
                    tp_devices = json.loads(values_dict["tp_devices"])
                    for tp_name_key, tp_data in tp_devices.iteritems():
                        if tp_name_key == tp_name_selected:
                            values_dict["updated_tp_device_name"] = tp_data["tp_name"]
                            if tp_data["mode"] == "D":
                                values_dict["action_device_variable_selection"] = "D"
                                values_dict["source_device_menu"] = int(tp_data["dev_id"])
                                values_dict["source_device_dim_action"] = bool(tp_data["dev_dim_action"])
                                supports_on_off_state = bool(tp_data["supports_on_off_state"])
                                values_dict["source_device_supports_on_off_state"] = supports_on_off_state
                                if supports_on_off_state:
                                    values_dict["create_tp_on_off_state"] = bool(tp_data["create_tp_on_off_state"])
                                supports_brightness_state = bool(tp_data["supports_brightness_state"])
                                values_dict["source_device_supports_brightness_state"] = supports_brightness_state
                                if supports_brightness_state:
                                    values_dict["create_tp_brightness_state"] = bool(tp_data["create_tp_brightness_state"])
                                supports_colourRGB_state = bool(tp_data["supports_colourRGB_state"])
                                values_dict["source_device_supports_colourRGB_state"] = supports_colourRGB_state
                                if supports_colourRGB_state:
                                    values_dict["create_tp_colourRGB_state"] = bool(tp_data["create_tp_colourRGB_state"])
                            elif tp_data["mode"] == "A":
                                values_dict["source_device_supports_on_off_state"] = False
                                values_dict["source_device_supports_brightness_state"] = False
                                values_dict["source_device_supports_colourRGB_state"] = False
                                values_dict["action_device_variable_selection"] = "A"
                                values_dict["source_action_group_menu"] = int(tp_data["action_group_id"])
                            elif tp_data["mode"] == "V":
                                values_dict["source_device_supports_on_off_state"] = False
                                values_dict["source_device_supports_brightness_state"] = False
                                values_dict["source_device_supports_colourRGB_state"] = False
                                values_dict["action_device_variable_selection"] = "V"
                                values_dict["source_variable_menu"] = int(tp_data["variable_id"])
                                values_dict["variable_state_type"] = "N"
                                values_dict["supports_variable_tp_true_false_state"] = False
                                values_dict["supports_variable_tp_text_state"] = False
                                values_dict["create_variable_tp_true_false_state"] = False
                                values_dict["create_variable_tp_text_state"] = False
                                if "variable_state_type" in tp_data:
                                    values_dict["variable_state_type"] = tp_data["variable_state_type"]
                                else:
                                    values_dict["variable_state_type"] = "N"
                                if values_dict["variable_state_type"] == "B":
                                    if "supports_variable_tp_true_false_state" in tp_data:
                                        values_dict["supports_variable_tp_true_false_state"] = bool(tp_data["supports_variable_tp_true_false_state"])
                                    if "create_variable_tptrue_false_state" in tp_data:
                                        values_dict["create_variable_tp_true_false_state"] = bool(tp_data["create_variable_tptrue_false_state"])
                                elif values_dict["variable_state_type"] == "T":
                                    if "supports_variable_tp_text_state" in tp_data:
                                        values_dict["supports_variable_tp_text_state"] = bool(tp_data["supports_variable_tp_text_state"])
                                    if "create_variable_tp_text_state" in tp_data:
                                        values_dict["create_variable_tp_text_state"] = bool(tp_data["create_variable_tp_text_state"])

        return values_dict

    # =============================================================================
    def tp_disconnect(self, dev):
        """
        Plugin method to process disconnection from Touch Portal Desktop App.

        -----
        :param dev:
        :return:
        """

        try:
            dev_id = dev.id

            disconnecting_status = ""  # Assume no bad disconnection state message

            # Check if TP Reader thread is running for this Touch Portal device and if so, stop it
            if dev_id in self.globals[K_THREADS]:
                if K_THREAD_READER in self.globals[K_THREADS][dev_id]:
                    try:
                        self.globals[K_THREADS][dev_id][K_THREAD_READER][K_EVENT].set()
                        self.globals[K_THREADS][dev_id][K_THREAD_READER][K_THREAD].join(timeout=3)  # Wait at least 'timeout' seconds for thread to end
                    except StandardError as standard_error_message:
                        self.logger.error(u"Error detected in Touch Portal Plugin [tp_disconnect of device "
                                          u"'{0}']. Line '{1}' has error='{2}'".format(dev.name,
                                                                                       sys.exc_traceback.tb_lineno,
                                                                                       standard_error_message))
                        disconnecting_status = u"Disconnecting thread error"  # Error clearing out previous TP Reader thread

            # Check if TP Handler thread is running for this Touch Portal device and if so, stop it
            if dev_id in self.globals[K_THREADS]:
                if K_THREAD_HANDLER in self.globals[K_THREADS][dev_id]:
                    try:
                        self.globals[K_THREADS][dev_id][K_THREAD_HANDLER][K_EVENT].set()
                        self.globals[K_THREADS][dev_id][K_THREAD_HANDLER][K_THREAD].join(timeout=3)  # Wait at least 'timeout' seconds for thread to end
                    except StandardError as standard_error_message:
                        self.logger.error(u"Error detected in Touch Portal Plugin [tp_disconnect of device "
                                          u"'{0}']. Line '{1}' has error='{2}'".format(dev.name,
                                                                                       sys.exc_traceback.tb_lineno,
                                                                                       standard_error_message))
                        disconnecting_status = u"Disconnecting thread error"  # Error clearing out previous TP Handler thread

            if disconnecting_status != "":
                dev.updateStateOnServer("connection_status", disconnecting_status)
                dev.setErrorStateOnServer("Connection Error")
                return False  # Error detected

            dev.updateStateOnServer("connection_status", "Disconnected")
            dev.updateStateOnServer("onOffState", False, uiValue="Disconnected", clearErrorState=True)
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

            return True  # All OK

        except StandardError as standard_error_message:
            self.logger.error(u"Error detected in Touch Portal Plugin [tp_disconnect of device '{0}']. "
                              u"Line '{1}' has error='{2}'".format(dev.name,
                                                                   sys.exc_traceback.tb_lineno,
                                                                   standard_error_message))
            return False

    # =============================================================================
    def update_tp_device(self, values_dict, type_id, dev_id):

        if values_dict["action_device_variable_selection"] == "D":
            indigo_dev_id = int(values_dict["source_device_menu"])
            if indigo_dev_id == 0:
                error_dict = indigo.Dict()
                error_dict["source_device_menu"] = u"Indigo Device not selected"
                error_dict["showAlertText"] = u"No Indigo Device selected."
                return values_dict, error_dict
            else:
                indigo_dev = indigo.devices[indigo_dev_id]
                tp_override_name = indigo_dev.name
        elif values_dict["action_device_variable_selection"] == "A":
            indigo_action_group_id = int(values_dict["source_action_group_menu"])
            if indigo_action_group_id == 0:
                error_dict = indigo.Dict()
                error_dict["source_action_group_menu"] = u"Indigo Action Group not selected"
                error_dict["showAlertText"] = u"No Indigo Action Group selected."
                return values_dict, error_dict
            else:
                indigo_action = indigo.actions[indigo_action_group_id]
                tp_override_name = indigo_action.name

        elif values_dict["action_device_variable_selection"] == "V":
            indigo_variable_id = int(values_dict["source_variable_menu"])
            if indigo_variable_id == 0:
                error_dict = indigo.Dict()
                error_dict["source_variable_menu"] = u"Indigo Variable not selected"
                error_dict["showAlertText"] = u"No Indigo Variable selected."
                return values_dict, error_dict
            else:
                indigo_variable = indigo.variables[indigo_variable_id]
                tp_override_name = indigo_variable.name

        else:
            error_dict = indigo.Dict()
            error_dict["action_device_variable_selection"] = u"Indigo Action / Device / Variable menu option not selected"
            error_dict["showAlertText"] = u"Indigo Action / Device / Variable menu option not selected"
            return values_dict, error_dict

        if values_dict["updated_tp_device_name"] == u"":
            values_dict["updated_tp_device_name"] = tp_override_name

        if '|' in values_dict["updated_tp_device_name"]:
            error_dict = indigo.Dict()
            error_dict["updated_tp_device_name"] = u"Touch Portal item name cannot contain a vertical bar (i.e. '|')"
            error_dict["showAlertText"] = u"Touch Portal item name cannot contain a vertical bar (i.e. '|')"
            return values_dict, error_dict

        if ',' in values_dict["updated_tp_device_name"]:
            error_dict = indigo.Dict()
            error_dict["updated_tp_device_name"] = u"Touch Portal item name cannot contain a comma."
            error_dict["showAlertText"] = u"New Touch Portal item name cannot contain a comma"
            return values_dict, error_dict

        if ';' in values_dict["new_tp_device_name"]:
            error_dict = indigo.Dict()
            error_dict["updated_tp_device_name"] = u"Touch Portal item name cannot contain a semicolon."
            error_dict["showAlertText"] = u"Touch Portal item name cannot contain a semicolon."
            return values_dict, error_dict

        updated_tp_device_name = values_dict["updated_tp_device_name"]
        updated_tp_device_name_key = updated_tp_device_name.lower()

        try:
            if "tp_devices" not in values_dict:
                values_dict["tp_devices"] = json.dumps({})  # Empty dictionary in JSON container
            tp_devices = json.loads(values_dict["tp_devices"])

            for tp_name_key, tp_data in tp_devices.iteritems():
                if updated_tp_device_name_key == tp_name_key and \
                        updated_tp_device_name_key != values_dict["tp_devices_list"]:
                    error_dict = indigo.Dict()
                    error_dict["updated_tp_device_name"] = u"Duplicate Touch Portal item name"
                    error_dict["showAlertText"] = u"Touch Portal Device Name '{0}' is already allocated.".format(
                        updated_tp_device_name)
                    return values_dict, error_dict

            tp_devices[updated_tp_device_name_key] = {}
            tp_devices[updated_tp_device_name_key]["tp_name"] = updated_tp_device_name

            if values_dict["action_device_variable_selection"] == "D":
                indigo_dev_id = int(values_dict["source_device_menu"])
                indigo_dev = indigo.devices[indigo_dev_id]
                tp_devices[updated_tp_device_name_key]["mode"] = "D"
                tp_devices[updated_tp_device_name_key]["dev_id"] = indigo_dev_id
                tp_devices[updated_tp_device_name_key]["dev_name"] = indigo_dev.name
                tp_devices[updated_tp_device_name_key]["dev_dim_action"] = bool(values_dict["source_device_dim_action"])

                if "onOffState" in indigo_dev.states:
                    tp_devices[updated_tp_device_name_key]["supports_on_off_state"] = True
                    tp_devices[updated_tp_device_name_key]["create_tp_on_off_state"] = bool(values_dict["create_tp_on_off_state"])
                else:
                    tp_devices[updated_tp_device_name_key]["supports_on_off_state"] = False

                if "brightnessLevel" in indigo_dev.states:
                    tp_devices[updated_tp_device_name_key]["supports_brightness_state"] = True
                    tp_devices[updated_tp_device_name_key]["create_tp_brightness_state"] = bool(values_dict["create_tp_brightness_state"])
                else:
                    tp_devices[updated_tp_device_name_key]["supports_brightness_state"] = False

                if not hasattr(indigo_dev, "supportsRGB")\
                        or not hasattr(indigo_dev, "supportsColor")\
                        or not indigo_dev.supportsRGB\
                        or not indigo_dev.supportsColor:  # Check device supports color
                    tp_devices[updated_tp_device_name_key]["supports_colourRGB_state"] = False
                else:
                    tp_devices[updated_tp_device_name_key]["supports_colourRGB_state"] = True
                    tp_devices[updated_tp_device_name_key]["create_tp_colourRGB_state"] = bool(values_dict["create_tp_colourRGB_state"])

            elif values_dict["action_device_variable_selection"] == "A":
                indigo_action_group_id = int(values_dict["source_action_group_menu"])
                tp_devices[updated_tp_device_name_key]["mode"] = 'A'
                tp_devices[updated_tp_device_name_key]['action_group_id'] = indigo_action_group_id
            elif values_dict["action_device_variable_selection"] == "V":
                indigo_variable_id = int(values_dict["source_variable_menu"])
                tp_devices[updated_tp_device_name_key]["mode"] = "V"
                tp_devices[updated_tp_device_name_key]['variable_id'] = indigo_variable_id

                tp_devices[updated_tp_device_name_key]["supports_variable_tp_true_false_state"] = False
                tp_devices[updated_tp_device_name_key]["supports_variable_tp_text_state"] = True
                tp_devices[updated_tp_device_name_key]["variable_state_type"] = "N"
                if "variable_state_type" in values_dict:
                    tp_devices[updated_tp_device_name_key]["variable_state_type"] = values_dict["variable_state_type"]
                    if values_dict["variable_state_type"] == "B":
                        tp_devices[updated_tp_device_name_key]["supports_variable_tp_text_state"] = False
                        tp_devices[updated_tp_device_name_key]["create_variable_tp_text_state"] = False
                        tp_devices[updated_tp_device_name_key]["supports_variable_tp_true_false_state"] = True
                        tp_devices[updated_tp_device_name_key]["create_variable_tp_true_false_state"] = True
                    elif values_dict["variable_state_type"] == "T":
                        tp_devices[updated_tp_device_name_key]["supports_variable_tp_true_false_state"] = False
                        tp_devices[updated_tp_device_name_key]["create_variable_tp_true_false_state"] = False
                        tp_devices[updated_tp_device_name_key]["supports_variable_tp_text_state"] = True
                        tp_devices[updated_tp_device_name_key]["create_variable_tp_text_state"] = True

            if values_dict["tp_devices_list"] != updated_tp_device_name_key:
                del tp_devices[values_dict["tp_devices_list"]]

            values_dict["tp_devices"] = json.dumps(tp_devices)

            update_time = datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d %H:%M:%S.%f')
            values_dict["tp_devices_last_updated_date_time"] = update_time

            self.initialise_device_config_dialogue(values_dict)

        except StandardError as err:
            self.logger.error(u"StandardError detected in update_tp_device for '{0}'. Line "
                              u"'{1}' has error='{2}'".format(indigo.devices[dev_id].name,
                                                              sys.exc_traceback.tb_lineno,
                                                              err))

        # self.logger.debug(u"update_tp_device: VALUES DICT = {0}".format(values_dict))
        return values_dict

    # =============================================================================
    def variables_to_list(self, filter="", values_dict=None, typeId="", targetId=0):
        # Set a default with id 0
        # Iterates through the action list

        variable_list = [(0, "-- Select Variable --")]
        for variable in indigo.variables:
            variable_list.append((variable.id, variable.name))
        return variable_list
