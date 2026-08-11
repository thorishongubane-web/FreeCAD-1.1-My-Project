#----------------------------------------------------------------
# Generated CMake target import file for configuration "Release".
#----------------------------------------------------------------

# Commands may need to know the format version.
set(CMAKE_IMPORT_FILE_VERSION 1)

# Import target "Shiboken6::shiboken6" for configuration "Release"
set_property(TARGET Shiboken6::shiboken6 APPEND PROPERTY IMPORTED_CONFIGURATIONS RELEASE)
set_target_properties(Shiboken6::shiboken6 PROPERTIES
  IMPORTED_LOCATION_RELEASE "${_IMPORT_PREFIX}/bin/shiboken6.exe"
  )

list(APPEND _cmake_import_check_targets Shiboken6::shiboken6 )
list(APPEND _cmake_import_check_files_for_Shiboken6::shiboken6 "${_IMPORT_PREFIX}/bin/shiboken6.exe" )

# Commands beyond this point should not need to know the version.
set(CMAKE_IMPORT_FILE_VERSION)
