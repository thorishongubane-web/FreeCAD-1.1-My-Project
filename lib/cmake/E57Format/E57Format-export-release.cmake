#----------------------------------------------------------------
# Generated CMake target import file for configuration "Release".
#----------------------------------------------------------------

# Commands may need to know the format version.
set(CMAKE_IMPORT_FILE_VERSION 1)

# Import target "E57Format" for configuration "Release"
set_property(TARGET E57Format APPEND PROPERTY IMPORTED_CONFIGURATIONS RELEASE)
set_target_properties(E57Format PROPERTIES
  IMPORTED_LINK_INTERFACE_LANGUAGES_RELEASE "CXX"
  IMPORTED_LOCATION_RELEASE "D:/a/FreeCAD/FreeCAD/package/rattler-build/.pixi/envs/default/Library/lib/E57Format.lib"
  )

list(APPEND _cmake_import_check_targets E57Format )
list(APPEND _cmake_import_check_files_for_E57Format "D:/a/FreeCAD/FreeCAD/package/rattler-build/.pixi/envs/default/Library/lib/E57Format.lib" )

# Commands beyond this point should not need to know the version.
set(CMAKE_IMPORT_FILE_VERSION)
