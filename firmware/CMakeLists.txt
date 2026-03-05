cmake_minimum_required(VERSION 3.16)

set(EXTRA_COMPONENT_DIRS
    "${CMAKE_SOURCE_DIR}/components"
)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)

project(m2_daq)

# Auto-generate SPIFFS image from web_ui/ and flash it with the firmware.
# Partition name "storage" must match partitions.csv.
spiffs_create_partition_image(storage ../../web_ui FLASH_IN_PROJECT)
