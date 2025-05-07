# Description: Constants for the Bambu API
from enum import (
    Enum,
)
import logging

LOGGER = logging.getLogger()


CURRENT_STAGE_IDS = {
    "default": "unknown",
    0: "printing",
    1: "auto_bed_leveling",
    2: "heatbed_preheating",
    3: "sweeping_xy_mech_mode",
    4: "changing_filament",
    5: "m400_pause",
    6: "paused_filament_runout",
    7: "heating_hotend",
    8: "calibrating_extrusion",
    9: "scanning_bed_surface",
    10: "inspecting_first_layer",
    11: "identifying_build_plate_type",
    12: "calibrating_micro_lidar",  # DUPLICATED?
    13: "homing_toolhead",
    14: "cleaning_nozzle_tip",
    15: "checking_extruder_temperature",
    16: "paused_user",
    17: "paused_front_cover_falling",
    18: "calibrating_micro_lidar",  # DUPLICATED?
    19: "calibrating_extrusion_flow",
    20: "paused_nozzle_temperature_malfunction",
    21: "paused_heat_bed_temperature_malfunction",
    22: "filament_unloading",
    23: "paused_skipped_step",
    24: "filament_loading",
    25: "calibrating_motor_noise",
    26: "paused_ams_lost",
    27: "paused_low_fan_speed_heat_break",
    28: "paused_chamber_temperature_control_error",
    29: "cooling_chamber",
    30: "paused_user_gcode",
    31: "motor_noise_showoff",
    32: "paused_nozzle_filament_covered_detected",
    33: "paused_cutter_error",
    34: "paused_first_layer_error",
    35: "paused_nozzle_clog",
    # X1 returns -1 for idle
    -1: "idle",  # DUPLICATED
    # P1 returns 255 for idle
    255: "idle",  # DUPLICATED
}
class BambuUrl(Enum):
    LOGIN = 1
    TFA_LOGIN = 2
    EMAIL_CODE = 3
    SMS_CODE = 4
    BIND = 5
    SLICER_SETTINGS = 6
    TASKS = 7
    PROJECTS = 8

BAMBU_URL = {
    BambuUrl.LOGIN: 'https://api.bambulab.com/v1/user-service/user/login',
    BambuUrl.TFA_LOGIN: 'https://bambulab.com/api/sign-in/tfa',
    BambuUrl.EMAIL_CODE: 'https://api.bambulab.com/v1/user-service/user/sendemail/code',
    BambuUrl.SMS_CODE: 'https://bambulab.cn/api/v1/user-service/user/sendsmscode',
    BambuUrl.BIND: 'https://api.bambulab.com/v1/iot-service/api/user/bind',
    BambuUrl.SLICER_SETTINGS: 'https://api.bambulab.com/v1/iot-service/api/slicer/setting?version=1.10.0.89',
    BambuUrl.TASKS: 'https://api.bambulab.com/v1/user-service/my/tasks',
    BambuUrl.PROJECTS: 'https://api.bambulab.com/v1/iot-service/api/user/project',
}