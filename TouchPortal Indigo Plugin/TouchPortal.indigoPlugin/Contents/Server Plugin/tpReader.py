#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Touch Portal [tpReader] © Autolog & DaveL17 2020
#

# noinspection PyUnresolvedReferences
# ============================== Native Imports ===============================
import json
import logging
import socket
import sys
import time
import threading

# ============================== Custom Imports ===============================
try:
    import indigo
except ImportError:
    pass

# ============================== Plugin Imports ===============================
from constants import *


# noinspection PyUnresolvedReferences,PyPep8Naming,PyPep8
class ThreadTpReader(threading.Thread):

    # This class handles Touch Portal processing

    def __init__(self, pluginGlobals, event, touchPortalDeviceId):

        threading.Thread.__init__(self)

        self.globals = pluginGlobals
        self.dev_id = touchPortalDeviceId
        self.tpr_logger = logging.getLogger("Plugin.TP_READER")
        self.tpr_logger.debug(u"Debugging Touch Portal Reader Thread")
        self.thread_stop = event

    # =============================================================================
    def handle_communication(self, dev):
        """
        Handle socket communication with Touch Portal Desktop App.
        Perform a while loop to read messages from the Torch Portal Desktop App.

        -----
        :param dev:
        :return:
        """
        try:
            dev_id = dev.id
            socket_error_message = ""

            self.globals[K_QUEUES][dev_id][K_RECEIVE_FROM_SEND_TO_TP].put(
                [QUEUE_PRIORITY_HIGH, 0, CMD_PROCESS_SEND_TP_MESSAGE, dev_id,
                 ['{"type":"pair", "id":"indigo_domotics_001"}']])

            while not self.thread_stop.is_set() and socket_error_message == "":
                # noinspection PyPep8,PyBroadException
                try:
                    # Start process to accept input from Touch Portal
                    try:
                        data_lines = self.globals[K_SOCKETS][dev_id][K_TP_SOCKET].recv(1024)
                    except socket.timeout:
                        pass  # The timeout, allows for checking self.thread_stop.is_set()
                    except socket.error as error_msg:
                        self.tpr_logger.error(u"Socket error detected in Touch Portal Plugin [Device '{0}']."
                                              " Line '{1}' has error='{2}'"
                                              .format(dev.name, sys.exc_traceback.tb_lineno, error_msg))
                        socket_error_message = u"'{0}'".format(error_msg)
                    else:
                        if len(data_lines) == 0:
                            self.tpr_logger.warning(u"Communication with Touch Portal Desktop has been lost!")
                            socket_error_message = "Communication has been lost"
                        else:
                            data_list = data_lines.splitlines()
                            for data in data_list:
                                self.tpr_logger.debug(u"RECEIVED DATA BEING QUEUED: {0}".format(data))

                                self.globals[K_QUEUES][dev_id][K_RECEIVE_FROM_SEND_TO_TP].put(
                                    [QUEUE_PRIORITY_HIGH, 0, CMD_PROCESS_RECEIVED_TP_MESSAGE, dev_id, [data]])

                except StandardError as standard_error_message:
                    self.tpr_logger.error(u"StandardError detected in TP Reader Reader. Line '{0}' has error='{1}'"
                                          .format(sys.exc_traceback.tb_lineno, standard_error_message))
                    socket_error_message = u"See Indigo Error Log"
                except Exception:  # Catch any other error
                    self.tpr_logger.error(u"Unexpected Exception detected in TP Reader Thread."
                                          " Line '{0}' has error='{1}'"
                                          .format(sys.exc_traceback.tb_lineno, sys.exc_info()[0]))
                    socket_error_message = u"See Indigo Error Log"

            dev.updateStateOnServer("onOffState", False, uiValue="Disconnected", clearErrorState=True)
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

            if socket_error_message != "":
                self.close_socket(dev)
                dev.updateStateOnServer("connection_status", socket_error_message)
                dev.setErrorStateOnServer("Connection Error")

                # Initiate socket recovery process - See runConcurrentThread
                self.globals[K_LOCK].acquire()  # Serialise update of 'recoveryInvoked' list
                self.globals[K_RECOVERY_INVOKED].append(dev.id)  # Add deviceID to recover list
                self.globals[K_LOCK].release()
            else:
                self.close_socket(dev)

        except StandardError as standard_error_message:
            self.tpr_logger.error(u"StandardError detected in TP Reader Thread - handleCommunication."
                                  u" Line '{0}' has error='{1}'"
                                  .format(sys.exc_traceback.tb_lineno, standard_error_message))

        # End of While loop and TP Reader thread will close down on return to invoking Run method

    def close_socket(self, dev):
        try:
            dev_id = dev.id
            self.tpr_logger.debug(u"SHUTTING DOWN AND CLOSING SOCKET")
            self.globals[K_SOCKETS][dev_id][K_TP_SOCKET].shutdown(socket.SHUT_RDWR)
            self.globals[K_SOCKETS][dev_id][K_TP_SOCKET].close()
        except socket.error as error_msg:
            self.tpr_logger.debug(u"Ignoring Shutdown/Close Socket error for device '{0}'."
                                  " Line '{1}' has error='{2}'"
                                  .format(dev.name, sys.exc_traceback.tb_lineno, error_msg))

        except StandardError as standard_error_message:
            self.tpr_logger.error(u"StandardError detected in TP Reader Thread - close_socket."
                                  " Line '{0}' has error='{1}'"
                                  .format(sys.exc_traceback.tb_lineno, standard_error_message))

    # =============================================================================
    def handle_connection(self, dev):
        """
        Handle socket connection to Touch Portal Desktop.

        -----
        :param dev:
        :return:
        """
        try:
            dev_id = dev.id

            socket_error_message = ""
            socket_error_message_long = ""

            if dev_id in self.globals[K_SOCKETS] and K_TP_SOCKET in self.globals[K_SOCKETS][dev_id]:
                try:
                    self.globals[K_SOCKETS][dev_id][K_TP_SOCKET].close()
                except socket.error as socket_error:
                    socket_error_message_long = (
                        u"Socket error detected in Touch Portal Plugin [handleConnection of device '{0}']."
                        u" Line '{1}' has error='{2}'"
                        .format(dev.name, sys.exc_traceback.tb_lineno, socket_error))
                    socket_error_message = u"'{0}'".format(socket_error)

            if socket_error_message == "":
                if self.dev_id not in self.globals[K_SOCKETS]:
                    self.globals[K_SOCKETS][dev_id] = {}
                try:
                    self.globals[K_SOCKETS][dev_id][K_TP_SOCKET] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.globals[K_SOCKETS][dev_id][K_TP_SOCKET].settimeout(self.globals[K_TP][dev_id][K_TIMEOUT])
                    self.globals[K_SOCKETS][dev_id][K_TP_SOCKET].connect(
                        (self.globals[K_TP][dev_id][K_HOST], self.globals[K_TP][dev_id][K_PORT]))
                except socket.error as socket_error:
                    socket_error_code = socket_error.errno
                    if socket_error_code == 61:
                        socket_error_message = u"Connection failed"
                        socket_error_message_long = u"Connection attempt to Touch Portal Desktop failed; Is it running?"
                    else:
                        socket_error_message = u"Connection failed: {0}".format(socket_error_code)
                        socket_error_message_long = u"Connection to Touch Portal Desktop failed with error: {0}"\
                            .format(socket_error)

            if socket_error_message != "":
                dev.updateStateOnServer("connection_status", socket_error_message)
                dev.setErrorStateOnServer("Connection Error")
                return False, socket_error_message_long   # Connection error

            dev.updateStateOnServer("onOffState", True, uiValue="Connected", clearErrorState=True)
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
            dev.updateStateOnServer("connection_status", "Connected")

            return True, "OK"  # Connected OK

        except StandardError as standard_error_message:
            self.tpr_logger.error(u"StandardError detected in TP Reader Thread - handleConnection."
                                  " Line '{0}' has error='{1}'"
                                  .format(sys.exc_traceback.tb_lineno, standard_error_message))
            return False

    # =============================================================================
    def run(self):
        """
        Run thread.
        """
        try:
            # Initialise routine on thread start

            dev_id = self.dev_id
            dev = indigo.devices[dev_id]

            self.tpr_logger.debug(u"Touch Portal Reader Thread initialised")

            self.globals[K_TP][dev_id][K_SOCKET_RETRY_SECONDS] = int(dev.pluginProps.get("socketRetrySeconds",
                                                                     TP_SOCKET_RETRY_DEFAULT))
            self.globals[K_TP][dev_id][K_SOCKET_RETRY_SILENT_AFTER] = int(dev.pluginProps.get("socketRetrySilentAfter",
                                                                          TP_SOCKET_RETRY_SILENT_AFTER_DEFAULT))

            retry_count = 0
            retry_visible_limit = int(self.globals[K_TP][dev_id][K_SOCKET_RETRY_SILENT_AFTER])
            retry_delay = int(self.globals[K_TP][dev_id][K_SOCKET_RETRY_SECONDS])

            self.tpr_logger.debug(u"RETRY [Before While Loop]: Count = {0}, Limit = {1}, Delay = {2}"
                                  .format(retry_count, retry_visible_limit, retry_delay))

            while not self.thread_stop.is_set():
                # Attempt connection to Touch Portal Desktop
                socket_connected, socket_error_message_long = self.handle_connection(dev)

                self.tpr_logger.debug(u"RETRY: socketConnected = {0}, socket_error_message_long = {1}"
                                      .format(socket_connected, socket_error_message_long))

                if socket_connected:
                    break  # Connection OK

                if retry_visible_limit >= retry_count:
                    if retry_count == 0:
                        self.tpr_logger.warning(socket_error_message_long)
                        self.tpr_logger.warning(
                            u"Will attempt to reconnect to Touch Portal Desktop every {0} seconds".format(retry_delay))
                    else:
                        self.tpr_logger.warning(u"Connection attempt {0}: {1}"
                                                .format(retry_count, socket_error_message_long))

                    if retry_visible_limit == retry_count:
                        self.tpr_logger.warning(
                            u"Suppressing retry connection messages (logging limit {0} has been reached)"
                            .format(retry_visible_limit))

                retry_count += 1
                self.tpr_logger.debug(u"RETRY [In While Loop]: Count = {0}, Limit = {1}, Delay = {2}"
                                      .format(retry_count, retry_visible_limit, retry_delay))
                time.sleep(retry_delay)  # Sleep and then continue While 'not connected' loop

            if not self.thread_stop.is_set():
                self.tpr_logger.info(u"'{0}' now connected to Touch Portal Desktop".format(dev.name))
                self.handle_communication(dev)

        except StandardError as standard_error_message:
            self.tpr_logger.error(u"StandardError detected in TP Reader Thread - Run. Line '{0}' has error='{1}'"
                                  .format(sys.exc_traceback.tb_lineno, standard_error_message))

        self.tpr_logger.debug(u"Touch Portal Reader Thread Ended")
