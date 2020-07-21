#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""
Loads the existing entry.tp file, adjusts the value of a setting, and writes
a (changed and renamed) copy.
Discord guys suggest that key order in entry.tp doesn't matter (key order is
not preserved from the example entry.tp file in the docs). That aspect is
untested.
Requires the file be stored in the usual location.
"""


# noinspection PyUnresolvedReferences
# ============================== Native Imports ===============================
import copy
import json
import sys

# ============================== Custom Imports ===============================
try:
    import indigo
except ImportError:
    pass

# ============================== Plugin Imports ===============================
from constants import *


# =============================================================================
def construct(plugin_self, dev_id):

    try:
        plugin_self.logger.debug(u"CONSTRUCT IS GO ...")  # TESTING ONLY :)

        path_to_file = ("{0}/{1}/entry.tp"
                        .format(plugin_self.globals[K_TP][dev_id][K_DESKTOP_USER_DATA_FOLDER_PATH],
                                TP_DESKTOP_PLUGIN_LOCATION))

        plugin_self.logger.debug(u"CONSTRUCT: Path To File is '{0}'".format(path_to_file))

        # If needed, can use the following code to load in the existing entry.tp file. Currently unused.
        # try:
        # Retrieve the existing entry.tp file.
        #     with open(path_to_file, 'r') as infile:
        #         entry_tp = json.load(infile)
        #
        # except IOError:
        #     pass

        # Re-initialise monitored devices and monitored variables
        plugin_self.globals[K_TP][K_MONITORED_DEVICES] = {}  # Dictionary will be filled with devices to monitor
        plugin_self.globals[K_TP][K_MONITORED_VARIABLES] = {}  # Dictionary will be filled with variables to monitor

        monitored_devices = {}  # Dictionary will be filled with devices to monitor
        monitored_variables = {}  # Dictionary will be filled with variables to monitor

        tp_state_id = u""
        tp_devices_pre_json = indigo.devices[dev_id].pluginProps.get("tp_devices", None)

        if tp_devices_pre_json is None:
            plugin_self.logger.debug(u"TP DEVICES MISSING")  # TODO: Needs Enhancing
            return False

        plugin_self.logger.debug(u"TP DEVICES PRE-JSON in entry_tp_generator:\n-- Start --\n{0}\n-- End --\n"
                                 .format(tp_devices_pre_json))

        tp_devices = json.loads(tp_devices_pre_json)

        tp_devices_supporting_device_on_off = []
        tp_devices_supporting_device_brightness = []
        tp_devices_supporting_device_colour_rgb = []
        tp_devices_supporting_action_group = []
        tp_devices_supporting_variable_on_off = []
        tp_devices_supporting_variable_text = []

        tp_devices_state_device_on_off_list = []
        tp_devices_state_device_brightness_list = []
        tp_devices_state_device_colour_rgb_list = []
        tp_devices_state_variable_on_off_list = []
        tp_devices_state_variable_text_list = []

        for tp_name_key, tp_data in tp_devices.iteritems():
            if tp_data["mode"] == 'D':

                if "supports_on_off_state" in tp_data and bool(tp_data["supports_on_off_state"]):
                    tp_devices_supporting_device_on_off.append(tp_data["tp_name"])
                if "supports_brightness_state" in tp_data and bool(tp_data["supports_brightness_state"]):
                    tp_devices_supporting_device_brightness.append(tp_data["tp_name"])
                if "supports_colourRGB_state" in tp_data and bool(tp_data["supports_colourRGB_state"]):
                    tp_devices_supporting_device_colour_rgb.append(tp_data["tp_name"])

                monitor_list = [dev_id, '', False, False, False]

                if "create_tp_on_off_state" in tp_data and bool(tp_data["create_tp_on_off_state"]):
                    tp_state_id = u"indigo_device_{0}_on_off".format(tp_data["dev_id"])
                    tp_event_id = u"indigo_device_{0}_on_off_event".format(tp_data["dev_id"])
                    tp_state_desc = u"{0} ON / OFF".format(tp_data["tp_name"])
                    tp_devices_state_device_on_off_list.append([tp_state_id, tp_state_desc, tp_event_id])
                    monitor_list[TP_MONITOR_ON_OFF] = True
                if "create_tp_brightness_state" in tp_data and bool(tp_data["create_tp_brightness_state"]):
                    tp_state_id = u"indigo_device_{0}_brightness".format(tp_data["dev_id"])
                    tp_state_desc = u"{0} BRIGHTNESS".format(tp_data["tp_name"])
                    tp_devices_state_device_brightness_list.append([tp_state_id, tp_state_desc])
                    monitor_list[TP_MONITOR_BRIGHTNESS] = True
                if "create_tp_colourRGB_state" in tp_data and bool(tp_data["create_tp_colourRGB_state"]):
                    tp_state_id = u"indigo_device_{0}_colour_rgb".format(tp_data["dev_id"])
                    tp_state_desc = u"{0} RGB".format(tp_data["tp_name"])
                    tp_devices_state_device_colour_rgb_list.append([tp_state_id, tp_state_desc])
                    monitor_list[TP_MONITOR_RGB] = True

                if monitor_list[TP_MONITOR_ON_OFF] or monitor_list[TP_MONITOR_BRIGHTNESS] or \
                        monitor_list[TP_MONITOR_RGB]:
                    monitor_list[TP_MONITOR_TP_STATE_ID] = tp_state_id
                    monitored_device_id = int(tp_data["dev_id"])
                    monitored_devices[monitored_device_id] = monitor_list

            elif tp_data["mode"] == 'A':
                tp_devices_supporting_action_group.append(tp_name_key)

            elif tp_data["mode"] == 'V':

                monitor_list = [dev_id, '', False, False]

                if "create_variable_tp_true_false_state" in tp_data and \
                        bool(tp_data["create_variable_tp_true_false_state"]):
                    tp_devices_supporting_variable_on_off.append(tp_data["tp_name"])
                    tp_state_id = u"indigo_variable_{0}_true_false".format(tp_data["variable_id"])
                    tp_event_id = u"indigo_variable_{0}_true_false_event".format(tp_data["variable_id"])
                    tp_state_desc = u"{0} 'true' / 'false".format(tp_data["tp_name"])
                    tp_devices_state_variable_on_off_list.append([tp_state_id, tp_state_desc, tp_event_id])
                    monitor_list[TP_MONITOR_ON_OFF] = True

                if "create_variable_tp_text_state" in tp_data and bool(tp_data["create_variable_tp_text_state"]):
                    tp_devices_supporting_variable_text.append(tp_data["tp_name"])
                    tp_state_id = u"indigo_variable_{0}_text".format(tp_data["variable_id"])
                    tp_state_desc = u"{0} TEXT".format(tp_data["tp_name"])
                    tp_devices_state_variable_text_list.append([tp_state_id, tp_state_desc])
                    monitor_list[TP_MONITOR_TEXT] = True

                if monitor_list[TP_MONITOR_ON_OFF] or monitor_list[TP_MONITOR_TEXT]:
                    monitor_list[TP_MONITOR_TP_STATE_ID] = tp_state_id
                    monitored_variable_id = int(tp_data["variable_id"])
                    monitored_variables[monitored_variable_id] = monitor_list

        tp_devices_device_on_off_default = "- Select Device -"
        tp_devices_device_on_off_list = [tp_devices_device_on_off_default]
        for tp_device_supporting_device_on_off in tp_devices_supporting_device_on_off:
            tp_devices_device_on_off_list.append(tp_device_supporting_device_on_off)
        if len(tp_devices_device_on_off_list) == 1:
            tp_devices_device_on_off_default = "- No Devices Defined -"
            tp_devices_device_on_off_list = [tp_devices_device_on_off_default]
        tp_devices_device_on_off_list.append("- Refresh Devices -")

        tp_devices_device_brightness_default = "- Select Device -"
        tp_devices_device_brightness_list = [tp_devices_device_brightness_default]
        for tp_device_supporting_device_brightness in tp_devices_supporting_device_brightness:
            tp_devices_device_brightness_list.append(tp_device_supporting_device_brightness)
        if len(tp_devices_device_brightness_list) == 1:
            tp_devices_device_brightness_default = "- No Devices Defined -"
            tp_devices_device_brightness_list = [tp_devices_device_brightness_default]
        tp_devices_device_brightness_list.append("- Refresh Devices -")

        tp_devices_device_colour_rgb_default = "- Select Device -"
        tp_devices_device_colour_rgb_list = [tp_devices_device_colour_rgb_default]
        for tp_device_supporting_device_colour_rgb in tp_devices_supporting_device_colour_rgb:
            tp_devices_device_colour_rgb_list.append(tp_device_supporting_device_colour_rgb)
        if len(tp_devices_device_colour_rgb_list) == 1:
            tp_devices_device_colour_rgb_default = "- No Devices Defined -"
            tp_devices_device_colour_rgb_list = [tp_devices_device_colour_rgb_default]
        tp_devices_device_colour_rgb_list.append("- Refresh Devices -")

        tp_devices_action_group_default = "- Select Action Group -"
        tp_devices_action_group_list = [tp_devices_action_group_default]
        for tp_device_supporting_action_group in tp_devices_supporting_action_group:
            tp_devices_action_group_list.append(tp_device_supporting_action_group)
        if len(tp_devices_action_group_list) == 1:
            tp_devices_action_group_default = "- No Action Groups Defined -"
            tp_devices_action_group_list = [tp_devices_action_group_default]
        tp_devices_action_group_list.append("- Refresh Action Groups -")

        tp_devices_variable_true_false_default = "- Select Variable -"
        tp_devices_variable_on_off_list = [tp_devices_variable_true_false_default]
        for tp_device_supporting_variable_on_off in tp_devices_supporting_variable_on_off:
            tp_devices_variable_on_off_list.append(tp_device_supporting_variable_on_off)
        if len(tp_devices_variable_on_off_list) == 1:
            tp_devices_variable_true_false_default = "- No Variables Defined -"
            tp_devices_variable_on_off_list = [tp_devices_variable_true_false_default]
        tp_devices_variable_on_off_list.append("- Refresh Variables -")

        tp_devices_variable_text_default = "- Select Variable -"
        tp_devices_variable_text_list = [tp_devices_variable_text_default]
        for tp_device_supporting_variable in tp_devices_supporting_variable_text:
            tp_devices_variable_text_list.append(tp_device_supporting_variable)
        if len(tp_devices_variable_text_list) == 1:
            tp_devices_variable_text_default = "- No Variables Defined -"
            tp_devices_variable_text_list = [tp_devices_variable_text_default]

        tp_devices_variable_text_list.append("- Refresh Variables -")

        plugin_self.logger.debug(u"TP_DEVICES_ON_OFF_LIST: {0}".format(tp_devices_device_on_off_list))
        plugin_self.logger.debug(u"TP_DEVICES_BRIGHTNESS_LIST: {0}".format(tp_devices_device_brightness_list))
        plugin_self.logger.debug(u"TP_DEVICES_COLOUR_RGB_LIST: {0}".format(tp_devices_device_colour_rgb_list))
        plugin_self.logger.debug(u"TP_DEVICES_ACTION_GROUPS_LIST: {0}".format(tp_devices_action_group_list))
        plugin_self.logger.debug(u"TP_DEVICES_VARIABLE_ON_OFF_LIST: {0}".format(tp_devices_variable_on_off_list))
        plugin_self.logger.debug(u"TP_DEVICES_VARIABLE_TEXT_LIST: {0}".format(tp_devices_variable_text_list))

        version = plugin_self.globals[K_TP_PLUGIN_INFO][K_TP_PLUGIN_VERSION]
        entry_tp = {'sdk': 2, 'version': version, 'name': "Indigo Domotics Plugin", 'id': "indigo_domotics_001",
                    'configuration': {'colorDark': "#330099", 'colorLight': "#6633FF"}}

        entry_tp['categories'] = [{'id': "indigo_devices", 'name': "Indigo Devices",
                                   'imagepath': "%TP_PLUGIN_FOLDER%Indigo Domotics/indigo_icon.png",
                                   'actions': [], 'events': [], 'states': []
                                   },
                                  {'id': "indigo_action_groups",
                                   'name': "Indigo Action Groups",
                                   'imagepath': "%TP_PLUGIN_FOLDER%Indigo Domotics/indigo_icon.png",
                                   'actions': []},
                                  {'id': "indigo_variables",
                                   'name': "Indigo Variables",
                                   'imagepath': "%TP_PLUGIN_FOLDER%Indigo Domotics/indigo_icon.png",
                                   'actions': [],
                                   'events': [],
                                   'states': []
                                   }
                                  ]

        actions_devices_ref = entry_tp['categories'][0]['actions']
        events_devices_ref = entry_tp['categories'][0]['events']
        states_devices_ref = entry_tp['categories'][0]['states']

        actions_action_groups_ref = entry_tp['categories'][1]['actions']
        # events_action_groups_ref = entry_tp['categories'][1]['events']
        # states_action_groups_ref = entry_tp['categories'][1]['states']

        actions_variables_ref = entry_tp['categories'][2]['actions']
        events_variables_ref = entry_tp['categories'][2]['events']
        states_variables_ref = entry_tp['categories'][2]['states']

        # Establish actions ===========================================================

        # Action: Device Turn On
        actions_devices_ref.append({'id': "indigo_device_turn_on",
                                    'prefix': "Perform Device Action:",
                                    'name': "Device - Turn On",
                                    'tryInline': "true",
                                    'type': "communicate",
                                    'format': "Turn ON Indigo Device {$indigo_device_name_on_off$}",
                                    'data': [{'id': "indigo_device_name_on_off",
                                              'type': "choice",
                                              'label': "Indigo Device",
                                              'default': tp_devices_device_on_off_default,
                                              'valueChoices': tp_devices_device_on_off_list}
                                             ]
                                    }
                                   )

        # Action: Device Turn Off
        actions_devices_ref.append({'id': "indigo_device_turn_off",
                                    'prefix': "Perform Device Action:",
                                    'name': "Device - Turn Off",
                                    'tryInline': "true",
                                    'type': "communicate",
                                    'format': "Turn OFF Indigo Device {$indigo_device_name_on_off$}",
                                    'data': [{'id': "indigo_device_name_on_off",
                                              'type': "choice",
                                              'label': "Indigo Device",
                                              'default': tp_devices_device_on_off_default,
                                              'valueChoices': tp_devices_device_on_off_list}
                                             ]
                                    }
                                   )

        # Action: Device Toggle
        actions_devices_ref.append({'id': "indigo_device_toggle",
                                    'prefix': "Perform Device Action:",
                                    'name': "Device - Toggle",
                                    'tryInline': "true", 'type': "communicate",
                                    'format': "Toggle ON/OFF Indigo Device {$indigo_device_name_on_off$}",
                                    'data': [{'id': "indigo_device_name_on_off",
                                              'type': "choice",
                                              'label': "Indigo Device",
                                              'default': tp_devices_device_on_off_default,
                                              'valueChoices': tp_devices_device_on_off_list}
                                             ]
                                    }
                                   )

        # Action: Device Set Brightness
        actions_devices_ref.append({'id': "indigo_device_brightness_set",
                                    'prefix': "Perform Device Action:",
                                    'name': "Device - Set Brightness",
                                    'tryInline': "true", 'type': "communicate",
                                    'format': "Set Indigo Device {$indigo_device_name_brightness$} to brightness "
                                              "{$indigo_device_brightness_value$}%",
                                    'data': [{'id': "indigo_device_name_brightness",
                                              'type': "choice",
                                              'label': "Indigo Device",
                                              'default': tp_devices_device_brightness_default,
                                              'valueChoices': tp_devices_device_brightness_list},
                                             {'id': "indigo_device_brightness_value",
                                              'type': "number",
                                              'allowDecimals': "false",
                                              'label': "Brightness Value %",
                                              'default': 0}
                                             ]
                                    }
                                   )

        # Action: Device Brighten
        actions_devices_ref.append({'id': "indigo_device_brighten",
                                    'prefix': "Perform Device Action:",
                                    'name': "Device - Brighten",
                                    'tryInline': "true",
                                    'type': "communicate",
                                    'format': "Brighten Indigo Device {$indigo_device_name_brightness$} by "
                                              "{$indigo_device_brighten_value$}%",
                                    'data': [{'id': "indigo_device_name_brightness",
                                              'type': "choice",
                                              'label': "Indigo Device",
                                              'default': tp_devices_device_brightness_default,
                                              'valueChoices': tp_devices_device_brightness_list
                                              },
                                             {'id': "indigo_device_brighten_value",
                                              'type': "number",
                                              'allowDecimals': "false",
                                              'label': "Brighten by %",
                                              'default': 0
                                              }
                                             ]
                                    }
                                   )

        # Action: Device Dim
        actions_devices_ref.append({'id': "indigo_device_dim",
                                    'prefix': "Perform Device Action:",
                                    'name': "Device - Dim",
                                    'tryInline': "true", 'type': "communicate",
                                    'format': "Dim Indigo Device {$indigo_device_name_brightness$} by "
                                              "{$indigo_device_dim_value$}%",
                                    'data': [{'id': "indigo_device_name_brightness",
                                              'type': "choice",
                                              'label': "Indigo Device",
                                              'default': tp_devices_device_brightness_default,
                                              'valueChoices': tp_devices_device_brightness_list},
                                             {'id': "indigo_device_dim_value",
                                              'type': "number",
                                              'allowDecimals': "false",
                                              'label': "Dim by %",
                                              'default': 0}
                                             ]
                                    }
                                   )

        # Action: Device Set Colour
        actions_devices_ref.append({'id': "indigo_device_colour_set",
                                    'prefix': "Perform Device Action:",
                                    'name': "Device - Set Colour",
                                    'tryInline': "true",
                                    'type': "communicate",
                                    'format': "Set Indigo Device {$indigo_device_name_rgb$} to colour "
                                              "{$indigo_device_colour_value$}",
                                    'data': [{'id': "indigo_device_name_rgb",
                                              'type': "choice",
                                              'label': "Indigo Device",
                                              'default': tp_devices_device_colour_rgb_default,
                                              'valueChoices': tp_devices_device_colour_rgb_list},
                                             {'id': "indigo_device_colour_value",
                                              'type': "color",
                                              'label': "Colour Selection",
                                              'default': '#000000FF'}
                                             ]
                                    }
                                   )

        # Action: Action Group Run
        actions_action_groups_ref.append({'id': "indigo_action_group_run",
                                          'prefix': "Do the following action:",
                                          'name': "Action Group - Run",
                                          'tryInline': "true",
                                          'type': "communicate",
                                          'format': "Run Indigo Action Group {$indigo_action_group_name$}",
                                          'data': [{'id': "indigo_action_group_name",
                                                    'type': "choice",
                                                    'label': "Indigo Action Group",
                                                    'default': tp_devices_action_group_default,
                                                    'valueChoices': tp_devices_action_group_list}
                                                   ]
                                          }
                                         )

        # Action: Variable Set Value [TEXT]
        actions_variables_ref.append({'id': "indigo_variable_set_text",
                                      'prefix': "Do the following action:",
                                      'name': "Variable - Set Value",
                                      'tryInline': "true",
                                      'type': "communicate",
                                      'format': "Set Indigo Variable {$indigo_variable_name_text$} to value "
                                                "{$indigo_variable_value$}",
                                      'data': [{'id': "indigo_variable_name_text",
                                                'type': "choice",
                                                'label': "Indigo Variable",
                                                'default': tp_devices_variable_text_default,
                                                'valueChoices': tp_devices_variable_text_list}
                                               ]
                                      }
                                     )

        # Action: Variable Set True
        actions_variables_ref.append({'id': "indigo_variable_set_true",
                                      'prefix': "Perform Variable Action:",
                                      'name': "Variable - Set True",
                                      'tryInline': "true",
                                      'type': "communicate",
                                      'format': "Set Indigo Variable {$indigo_variable_name_true_false$} to 'true''",
                                      'data': [{'id': "indigo_variable_name_true_false",
                                                'type': "choice",
                                                'label': "Indigo Variable",
                                                'default': tp_devices_variable_true_false_default,
                                                'valueChoices': tp_devices_variable_on_off_list}
                                               ]
                                      }
                                     )

        # Action: Variable Set False
        actions_variables_ref.append({'id': "indigo_variable_set_false",
                                      'prefix': "Perform Variable Action:",
                                      'name': "Variable - Set False",
                                      'tryInline': "true",
                                      'type': "communicate",
                                      'format': "Set Indigo Variable {$indigo_variable_name_true_false$} to 'false''",
                                      'data': [{'id': "indigo_variable_name_true_false",
                                                'type': "choice",
                                                'label': "Indigo Variable",
                                                'default': tp_devices_variable_true_false_default,
                                                'valueChoices': tp_devices_variable_on_off_list}
                                               ]
                                      }
                                     )

        # Action: Variable Toggle
        actions_variables_ref.append({'id': "indigo_variable_toggle",
                                      'prefix': "Perform Variable Action:",
                                      'name': "Variable - Toggle",
                                      'tryInline': "true",
                                      'type': "communicate",
                                      'format': "Toggle 'true'/'false' Indigo Variable "
                                                "{$indigo_variable_name_true_false$}",
                                      'data': [{'id': "indigo_variable_name_true_false",
                                                'type': "choice",
                                                'label': "Indigo Variable",
                                                'default': tp_devices_variable_true_false_default,
                                                'valueChoices': tp_devices_variable_on_off_list}
                                               ]
                                      }
                                     )

        # Establish events ============================================================
        for tp_device_state_on_off in tp_devices_state_device_on_off_list:
            tp_state_id = tp_device_state_on_off[0]
            tp_event_id = tp_device_state_on_off[2]
            tp_event_desc = u"When {0} changes".format(tp_device_state_on_off[1])
            tp_event_format = "When {0} changes to $val".format(tp_device_state_on_off[1])
            events_devices_ref.append({'id': tp_event_id, 'name': tp_event_desc, 'format': tp_event_format,
                                       'type': "communicate", 'valueType': "choice",
                                       'valueChoices': ["ON", "OFF"], 'valueStateId': tp_state_id})

        for tp_variable_state_true_false in tp_devices_state_variable_on_off_list:
            tp_state_id = tp_variable_state_true_false[0]
            tp_event_id = tp_variable_state_true_false[2]
            tp_event_desc = u"When {0} changes".format(tp_variable_state_true_false[1])
            tp_event_format = "When {0} changes to $val".format(tp_variable_state_true_false[1])
            events_variables_ref.append({'id': tp_event_id, 'name': tp_event_desc, 'format': tp_event_format,
                                         'type': "communicate", 'valueType': "choice",
                                         'valueChoices': ["true", "false"], 'valueStateId': tp_state_id})

        # Establish States ============================================================

        for tp_device_state_on_off in tp_devices_state_device_on_off_list:
            tp_state_id = tp_device_state_on_off[0]
            tp_state_desc = tp_device_state_on_off[1]
            states_devices_ref.append({'id': tp_state_id, 'type': "choice", 'desc': tp_state_desc, 'default': "OFF",
                                       'valueChoices': ["ON", "OFF"]})

        for tp_device_state_brightness in tp_devices_state_device_brightness_list:
            tp_state_id = tp_device_state_brightness[0]
            tp_state_desc = tp_device_state_brightness[1]
            states_devices_ref.append({'id': tp_state_id, 'type': "text", 'desc': tp_state_desc, 'default': "0"})

        for tp_device_state_colour_rgb in tp_devices_state_device_colour_rgb_list:
            tp_state_id = tp_device_state_colour_rgb[0]
            tp_state_desc = tp_device_state_colour_rgb[1]
            states_devices_ref.append({'id': tp_state_id, 'type': "text", 'desc': tp_state_desc,
                                       'default': "#4488CCFF"})

        for tp_variable_state_true_false in tp_devices_state_variable_on_off_list:
            tp_state_id = tp_variable_state_true_false[0]
            tp_state_desc = tp_variable_state_true_false[1]
            states_variables_ref.append({'id': tp_state_id, 'type': "choice", 'desc': tp_state_desc, 'default': "FALSE",
                                         'valueChoices': ["true", "false"]})

        for tp_variable_state_text in tp_devices_state_variable_text_list:
            tp_state_id = tp_variable_state_text[0]
            tp_state_desc = tp_variable_state_text[1]
            states_variables_ref.append({'id': tp_state_id, 'type': "text", 'desc': tp_state_desc, 'default': ""})

        try:
            # Write out the changed version.
            with open(u"{0}".format(path_to_file), 'w') as outfile:
                outfile.write(json.dumps(entry_tp, sort_keys=True, indent=2))
        except IOError as io_error:
            plugin_self.logger.error(u"CONSTRUCT ERROR: IOError is '{0}'".format(io_error))
            return False

        # plugin_self.globals[K_LOCK].acquire()  # Serialise update of monitored devices and variables
        plugin_self.globals[K_TP][K_MONITORED_DEVICES] = copy.deepcopy(monitored_devices)
        plugin_self.globals[K_TP][K_MONITORED_VARIABLES] = copy.deepcopy(monitored_variables)
        # plugin_self.globals[K_LOCK].release()

        plugin_self.logger.debug(u"K_MONITORED_DEVICES:\n{0}\n"
                                 .format(plugin_self.globals[K_TP][K_MONITORED_DEVICES]))
        plugin_self.logger.debug(u"K_MONITORED_VARIABLES:\n{0}\n"
                                 .format(plugin_self.globals[K_TP][K_MONITORED_VARIABLES]))

        return True

    except StandardError as standard_error_message:
        plugin_self.logger.error(
            u"CONSTRUCT ERROR: Standard error detected. Line '{0}' has error='{1}'"
            .format(sys.exc_traceback.tb_lineno, standard_error_message))
        return False
