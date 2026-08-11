#----------------------------------------------------------------
# Generated CMake target import file for configuration "Release".
#----------------------------------------------------------------

# Commands may need to know the format version.
set(CMAKE_IMPORT_FILE_VERSION 1)

# Import target "flann::flann_cpp" for configuration "Release"
set_property(TARGET flann::flann_cpp APPEND PROPERTY IMPORTED_CONFIGURATIONS RELEASE)
set_target_properties(flann::flann_cpp PROPERTIES
  IMPORTED_IMPLIB_RELEASE "${_IMPORT_PREFIX}/lib/flann_cpp.lib"
  IMPORTED_LINK_INTERFACE_LIBRARIES_RELEASE "D:/a/FreeCAD/FreeCAD/package/rattler-build/.pixi/envs/default/Library/lib/lz4.lib"
  IMPORTED_LOCATION_RELEASE "${_IMPORT_PREFIX}/bin/flann_cpp.dll"
  )

list(APPEND _cmake_import_check_targets flann::flann_cpp )
list(APPEND _cmake_import_check_files_for_flann::flann_cpp "${_IMPORT_PREFIX}/lib/flann_cpp.lib" "${_IMPORT_PREFIX}/bin/flann_cpp.dll" )

# Import target "flann::flann_cpp_s" for configuration "Release"
set_property(TARGET flann::flann_cpp_s APPEND PROPERTY IMPORTED_CONFIGURATIONS RELEASE)
set_target_properties(flann::flann_cpp_s PROPERTIES
  IMPORTED_LINK_INTERFACE_LANGUAGES_RELEASE "CXX"
  IMPORTED_LINK_INTERFACE_LIBRARIES_RELEASE "D:/a/FreeCAD/FreeCAD/package/rattler-build/.pixi/envs/default/Library/lib/lz4.lib"
  IMPORTED_LOCATION_RELEASE "${_IMPORT_PREFIX}/lib/flann_cpp_s.lib"
  )

list(APPEND _cmake_import_check_targets flann::flann_cpp_s )
list(APPEND _cmake_import_check_files_for_flann::flann_cpp_s "${_IMPORT_PREFIX}/lib/flann_cpp_s.lib" )

# Import target "flann::flann" for configuration "Release"
set_property(TARGET flann::flann APPEND PROPERTY IMPORTED_CONFIGURATIONS RELEASE)
set_target_properties(flann::flann PROPERTIES
  IMPORTED_IMPLIB_RELEASE "${_IMPORT_PREFIX}/lib/flann.lib"
  IMPORTED_LINK_INTERFACE_LIBRARIES_RELEASE "D:/a/FreeCAD/FreeCAD/package/rattler-build/.pixi/envs/default/Library/lib/lz4.lib"
  IMPORTED_LOCATION_RELEASE "${_IMPORT_PREFIX}/bin/flann.dll"
  )

list(APPEND _cmake_import_check_targets flann::flann )
list(APPEND _cmake_import_check_files_for_flann::flann "${_IMPORT_PREFIX}/lib/flann.lib" "${_IMPORT_PREFIX}/bin/flann.dll" )

# Import target "flann::flann_s" for configuration "Release"
set_property(TARGET flann::flann_s APPEND PROPERTY IMPORTED_CONFIGURATIONS RELEASE)
set_target_properties(flann::flann_s PROPERTIES
  IMPORTED_LINK_INTERFACE_LANGUAGES_RELEASE "CXX"
  IMPORTED_LINK_INTERFACE_LIBRARIES_RELEASE "D:/a/FreeCAD/FreeCAD/package/rattler-build/.pixi/envs/default/Library/lib/lz4.lib"
  IMPORTED_LOCATION_RELEASE "${_IMPORT_PREFIX}/lib/flann_s.lib"
  )

list(APPEND _cmake_import_check_targets flann::flann_s )
list(APPEND _cmake_import_check_files_for_flann::flann_s "${_IMPORT_PREFIX}/lib/flann_s.lib" )

# Commands beyond this point should not need to know the version.
set(CMAKE_IMPORT_FILE_VERSION)
