#----------------------------------------------------------------
# Generated CMake target import file for configuration "Release".
#----------------------------------------------------------------

# Commands may need to know the format version.
set(CMAKE_IMPORT_FILE_VERSION 1)

# Import target "Qt6::QuickVectorImage" for configuration "Release"
set_property(TARGET Qt6::QuickVectorImage APPEND PROPERTY IMPORTED_CONFIGURATIONS RELEASE)
set_target_properties(Qt6::QuickVectorImage PROPERTIES
  IMPORTED_IMPLIB_RELEASE "${_IMPORT_PREFIX}/lib/Qt6QuickVectorImage.lib"
  IMPORTED_LINK_DEPENDENT_LIBRARIES_RELEASE "Qt6::QuickVectorImageGeneratorPrivate;Qt6::Qml"
  IMPORTED_LOCATION_RELEASE "${_IMPORT_PREFIX}/lib/qt6/bin/Qt6QuickVectorImage.dll"
  )

list(APPEND _cmake_import_check_targets Qt6::QuickVectorImage )
list(APPEND _cmake_import_check_files_for_Qt6::QuickVectorImage "${_IMPORT_PREFIX}/lib/Qt6QuickVectorImage.lib" "${_IMPORT_PREFIX}/lib/qt6/bin/Qt6QuickVectorImage.dll" )

# Commands beyond this point should not need to know the version.
set(CMAKE_IMPORT_FILE_VERSION)
