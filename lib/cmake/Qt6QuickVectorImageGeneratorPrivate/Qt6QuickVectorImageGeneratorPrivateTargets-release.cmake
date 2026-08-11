#----------------------------------------------------------------
# Generated CMake target import file for configuration "Release".
#----------------------------------------------------------------

# Commands may need to know the format version.
set(CMAKE_IMPORT_FILE_VERSION 1)

# Import target "Qt6::QuickVectorImageGeneratorPrivate" for configuration "Release"
set_property(TARGET Qt6::QuickVectorImageGeneratorPrivate APPEND PROPERTY IMPORTED_CONFIGURATIONS RELEASE)
set_target_properties(Qt6::QuickVectorImageGeneratorPrivate PROPERTIES
  IMPORTED_IMPLIB_RELEASE "${_IMPORT_PREFIX}/lib/Qt6QuickVectorImageGenerator.lib"
  IMPORTED_LINK_DEPENDENT_LIBRARIES_RELEASE "Qt6::Core;Qt6::QuickShapesPrivate"
  IMPORTED_LOCATION_RELEASE "${_IMPORT_PREFIX}/lib/qt6/bin/Qt6QuickVectorImageGenerator.dll"
  )

list(APPEND _cmake_import_check_targets Qt6::QuickVectorImageGeneratorPrivate )
list(APPEND _cmake_import_check_files_for_Qt6::QuickVectorImageGeneratorPrivate "${_IMPORT_PREFIX}/lib/Qt6QuickVectorImageGenerator.lib" "${_IMPORT_PREFIX}/lib/qt6/bin/Qt6QuickVectorImageGenerator.dll" )

# Commands beyond this point should not need to know the version.
set(CMAKE_IMPORT_FILE_VERSION)
