#----------------------------------------------------------------
# Generated CMake target import file for configuration "Release".
#----------------------------------------------------------------

# Commands may need to know the format version.
set(CMAKE_IMPORT_FILE_VERSION 1)

# Import target "libaec::aec-shared" for configuration "Release"
set_property(TARGET libaec::aec-shared APPEND PROPERTY IMPORTED_CONFIGURATIONS RELEASE)
set_target_properties(libaec::aec-shared PROPERTIES
  IMPORTED_IMPLIB_RELEASE "${_IMPORT_PREFIX}/lib/aec.lib"
  IMPORTED_LOCATION_RELEASE "${_IMPORT_PREFIX}/bin/aec.dll"
  )

list(APPEND _cmake_import_check_targets libaec::aec-shared )
list(APPEND _cmake_import_check_files_for_libaec::aec-shared "${_IMPORT_PREFIX}/lib/aec.lib" "${_IMPORT_PREFIX}/bin/aec.dll" )

# Import target "libaec::sz-shared" for configuration "Release"
set_property(TARGET libaec::sz-shared APPEND PROPERTY IMPORTED_CONFIGURATIONS RELEASE)
set_target_properties(libaec::sz-shared PROPERTIES
  IMPORTED_IMPLIB_RELEASE "${_IMPORT_PREFIX}/lib/szip.lib"
  IMPORTED_LOCATION_RELEASE "${_IMPORT_PREFIX}/bin/szip.dll"
  )

list(APPEND _cmake_import_check_targets libaec::sz-shared )
list(APPEND _cmake_import_check_files_for_libaec::sz-shared "${_IMPORT_PREFIX}/lib/szip.lib" "${_IMPORT_PREFIX}/bin/szip.dll" )

# Commands beyond this point should not need to know the version.
set(CMAKE_IMPORT_FILE_VERSION)
