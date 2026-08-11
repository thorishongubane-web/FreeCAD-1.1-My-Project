set(_vtk_module_find_package_quiet)
if (${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
  set(_vtk_module_find_package_quiet QUIET)
endif ()

set(_vtk_module_find_package_components_checked)
set(_vtk_module_find_package_components_to_check
  ${${CMAKE_FIND_PACKAGE_NAME}_FIND_COMPONENTS})
set(_vtk_module_find_package_components)
set(_vtk_module_find_package_components_required)
while (_vtk_module_find_package_components_to_check)
  list(GET _vtk_module_find_package_components_to_check 0 _vtk_module_component)
  list(REMOVE_AT _vtk_module_find_package_components_to_check 0)
  if (_vtk_module_component IN_LIST _vtk_module_find_package_components_checked)
    continue ()
  endif ()
  list(APPEND _vtk_module_find_package_components_checked
    "${_vtk_module_component}")

  list(APPEND _vtk_module_find_package_components
    "${_vtk_module_component}")
  if (${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED_${_vtk_module_component})
    list(APPEND _vtk_module_find_package_components_required
      "${_vtk_module_component}")
  endif ()

  if (TARGET "${CMAKE_FIND_PACKAGE_NAME}::${_vtk_module_component}")
    set(_vtk_module_find_package_component_target "${CMAKE_FIND_PACKAGE_NAME}::${_vtk_module_component}")
  elseif (TARGET "${_vtk_module_component}")
    set(_vtk_module_find_package_component_target "${_vtk_module_component}")
  else ()
    # No such target for the component; skip.
    continue ()
  endif ()
  get_property(_vtk_module_find_package_depends
    TARGET    "${_vtk_module_find_package_component_target}"
    PROPERTY  "INTERFACE_vtk_module_depends")
  string(REPLACE "${CMAKE_FIND_PACKAGE_NAME}::" "" _vtk_module_find_package_depends "${_vtk_module_find_package_depends}")
  list(APPEND _vtk_module_find_package_components_to_check
    ${_vtk_module_find_package_depends})
  get_property(_vtk_module_find_package_depends
    TARGET    "${_vtk_module_find_package_component_target}"
    PROPERTY  "INTERFACE_vtk_module_private_depends")
  string(REPLACE "${CMAKE_FIND_PACKAGE_NAME}::" "" _vtk_module_find_package_depends "${_vtk_module_find_package_depends}")
  list(APPEND _vtk_module_find_package_components_to_check
    ${_vtk_module_find_package_depends})
  get_property(_vtk_module_find_package_depends
    TARGET    "${_vtk_module_find_package_component_target}"
    PROPERTY  "INTERFACE_vtk_module_optional_depends")
  foreach (_vtk_module_find_package_depend IN LISTS _vtk_module_find_package_depends)
    if (TARGET "${_vtk_module_find_package_depend}")
      string(REPLACE "${CMAKE_FIND_PACKAGE_NAME}::" "" _vtk_module_find_package_depend "${_vtk_module_find_package_depend}")
      list(APPEND _vtk_module_find_package_components_to_check
        "${_vtk_module_find_package_depend}")
    endif ()
  endforeach ()
  get_property(_vtk_module_find_package_depends
    TARGET    "${_vtk_module_find_package_component_target}"
    PROPERTY  "INTERFACE_vtk_module_forward_link")
  string(REPLACE "${CMAKE_FIND_PACKAGE_NAME}::" "" _vtk_module_find_package_depends "${_vtk_module_find_package_depends}")
  list(APPEND _vtk_module_find_package_components_to_check
    ${_vtk_module_find_package_depends})

  get_property(_vtk_module_find_package_kit
    TARGET    "${_vtk_module_find_package_component_target}"
    PROPERTY  "INTERFACE_vtk_module_kit")
  if (_vtk_module_find_package_kit)
    get_property(_vtk_module_find_package_kit_modules
      TARGET    "${_vtk_module_find_package_kit}"
      PROPERTY  "INTERFACE_vtk_kit_kit_modules")
    string(REPLACE "${CMAKE_FIND_PACKAGE_NAME}::" "" _vtk_module_find_package_kit_modules "${_vtk_module_find_package_kit_modules}")
    list(APPEND _vtk_module_find_package_components_to_check
      ${_vtk_module_find_package_kit_modules})
  endif ()
endwhile ()
unset(_vtk_module_find_package_component_target)
unset(_vtk_module_find_package_components_to_check)
unset(_vtk_module_find_package_components_checked)
unset(_vtk_module_component)
unset(_vtk_module_find_package_depend)
unset(_vtk_module_find_package_depends)
unset(_vtk_module_find_package_kit)
unset(_vtk_module_find_package_kit_modules)

if (_vtk_module_find_package_components)
  list(REMOVE_DUPLICATES _vtk_module_find_package_components)
endif ()
if (_vtk_module_find_package_components_required)
  list(REMOVE_DUPLICATES _vtk_module_find_package_components_required)
endif ()

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("Python" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("Python" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(Python3
    3.11
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          Interpreter;Development.Module
    OPTIONAL_COMPONENTS Development.Embed)
  if (NOT Python3_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: Python3")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_Python_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_Python_NOT_FOUND_MESSAGE"
      "Failed to find the Python3 package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("loguru" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("loguru" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(Threads
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT Threads_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: Threads")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_loguru_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_loguru_NOT_FOUND_MESSAGE"
      "Failed to find the Threads package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("RenderingQt" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("RenderingQt" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(Qt6
    6.8
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          Widgets
    OPTIONAL_COMPONENTS )
  if (NOT Qt6_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: Qt6")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_RenderingQt_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_RenderingQt_NOT_FOUND_MESSAGE"
      "Failed to find the Qt6 package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("glew" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("glew" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(GLEW
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT GLEW_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: GLEW")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_glew_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_glew_NOT_FOUND_MESSAGE"
      "Failed to find the GLEW package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("opengl" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("opengl" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(OpenGL
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          OpenGL
    OPTIONAL_COMPONENTS )
  if (NOT OpenGL_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: OpenGL")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_opengl_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_opengl_NOT_FOUND_MESSAGE"
      "Failed to find the OpenGL package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("libxml2" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("libxml2" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(LibXml2
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT LibXml2_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: LibXml2")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_libxml2_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_libxml2_NOT_FOUND_MESSAGE"
      "Failed to find the LibXml2 package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("hdf5" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("hdf5" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(HDF5
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          C;HL
    OPTIONAL_COMPONENTS )
  if (NOT HDF5_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: HDF5")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_hdf5_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_hdf5_NOT_FOUND_MESSAGE"
      "Failed to find the HDF5 package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("utf8" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("utf8" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(utf8cpp
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT utf8cpp_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: utf8cpp")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_utf8_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_utf8_NOT_FOUND_MESSAGE"
      "Failed to find the utf8cpp package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("xdmf3" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("xdmf3" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(Boost
    1.86.0
    EXACT
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT Boost_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: Boost")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_xdmf3_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_xdmf3_NOT_FOUND_MESSAGE"
      "Failed to find the Boost package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("jsoncpp" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("jsoncpp" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(JsonCpp
    0.7.0
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT JsonCpp_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: JsonCpp")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_jsoncpp_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_jsoncpp_NOT_FOUND_MESSAGE"
      "Failed to find the JsonCpp package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("theora" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("theora" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(THEORA
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT THEORA_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: THEORA")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_theora_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_theora_NOT_FOUND_MESSAGE"
      "Failed to find the THEORA package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("ogg" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("ogg" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(OGG
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT OGG_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: OGG")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_ogg_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_ogg_NOT_FOUND_MESSAGE"
      "Failed to find the OGG package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("netcdf" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("netcdf" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(NetCDF
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT NetCDF_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: NetCDF")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_netcdf_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_netcdf_NOT_FOUND_MESSAGE"
      "Failed to find the NetCDF package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("libproj" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("libproj" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(LibPROJ
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT LibPROJ_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: LibPROJ")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_libproj_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_libproj_NOT_FOUND_MESSAGE"
      "Failed to find the LibPROJ package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("zlib" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("zlib" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(ZLIB
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT ZLIB_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: ZLIB")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_zlib_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_zlib_NOT_FOUND_MESSAGE"
      "Failed to find the ZLIB package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("ioss" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("ioss" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(Threads
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT Threads_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: Threads")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_ioss_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_ioss_NOT_FOUND_MESSAGE"
      "Failed to find the Threads package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("exodusII" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("exodusII" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(Threads
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT Threads_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: Threads")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_exodusII_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_exodusII_NOT_FOUND_MESSAGE"
      "Failed to find the Threads package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("gl2ps" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("gl2ps" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(GL2PS
    1.4.2
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT GL2PS_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: GL2PS")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_gl2ps_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_gl2ps_NOT_FOUND_MESSAGE"
      "Failed to find the GL2PS package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("png" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("png" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(PNG
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT PNG_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: PNG")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_png_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_png_NOT_FOUND_MESSAGE"
      "Failed to find the PNG package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("nlohmannjson" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("nlohmannjson" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(nlohmann_json
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT nlohmann_json_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: nlohmann_json")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_nlohmannjson_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_nlohmannjson_NOT_FOUND_MESSAGE"
      "Failed to find the nlohmann_json package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("pugixml" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("pugixml" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(pugixml
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT pugixml_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: pugixml")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_pugixml_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_pugixml_NOT_FOUND_MESSAGE"
      "Failed to find the pugixml package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("sqlite" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("sqlite" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(SQLite3
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT SQLite3_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: SQLite3")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_sqlite_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_sqlite_NOT_FOUND_MESSAGE"
      "Failed to find the SQLite3 package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("GUISupportQt" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("GUISupportQt" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(Qt6
    6.8
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          OpenGL;Widgets;OpenGLWidgets
    OPTIONAL_COMPONENTS )
  if (NOT Qt6_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: Qt6")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_GUISupportQt_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_GUISupportQt_NOT_FOUND_MESSAGE"
      "Failed to find the Qt6 package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("eigen" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("eigen" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(Eigen3
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT Eigen3_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: Eigen3")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_eigen_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_eigen_NOT_FOUND_MESSAGE"
      "Failed to find the Eigen3 package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("RenderingOpenGL2" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("RenderingOpenGL2" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(DirectX
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT DirectX_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: DirectX")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_RenderingOpenGL2_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_RenderingOpenGL2_NOT_FOUND_MESSAGE"
      "Failed to find the DirectX package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("expat" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("expat" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(EXPAT
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT EXPAT_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: EXPAT")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_expat_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_expat_NOT_FOUND_MESSAGE"
      "Failed to find the EXPAT package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("doubleconversion" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("doubleconversion" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(double-conversion
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT double-conversion_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: double-conversion")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_doubleconversion_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_doubleconversion_NOT_FOUND_MESSAGE"
      "Failed to find the double-conversion package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("lz4" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("lz4" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(LZ4
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT LZ4_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: LZ4")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_lz4_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_lz4_NOT_FOUND_MESSAGE"
      "Failed to find the LZ4 package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("lzma" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("lzma" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(LZMA
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT LZMA_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: LZMA")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_lzma_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_lzma_NOT_FOUND_MESSAGE"
      "Failed to find the LZMA package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("jpeg" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("jpeg" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(JPEG
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT JPEG_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: JPEG")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_jpeg_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_jpeg_NOT_FOUND_MESSAGE"
      "Failed to find the JPEG package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("tiff" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("tiff" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(TIFF
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT TIFF_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: TIFF")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_tiff_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_tiff_NOT_FOUND_MESSAGE"
      "Failed to find the TIFF package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("freetype" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("freetype" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(Freetype
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT Freetype_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: Freetype")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_freetype_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_freetype_NOT_FOUND_MESSAGE"
      "Failed to find the Freetype package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("CommonSystem" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("CommonSystem" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(Threads
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT Threads_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: Threads")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_CommonSystem_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_CommonSystem_NOT_FOUND_MESSAGE"
      "Failed to find the Threads package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

set(_vtk_module_find_package_enabled OFF)
set(_vtk_module_find_package_is_required OFF)
set(_vtk_module_find_package_fail_if_not_found OFF)
if (_vtk_module_find_package_components)
  if ("CommonCore" IN_LIST _vtk_module_find_package_components)
    set(_vtk_module_find_package_enabled ON)
    if ("CommonCore" IN_LIST _vtk_module_find_package_components_required)
      set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
      set(_vtk_module_find_package_fail_if_not_found ON)
    endif ()
  endif ()
else ()
  set(_vtk_module_find_package_enabled ON)
  set(_vtk_module_find_package_is_required "${${CMAKE_FIND_PACKAGE_NAME}_FIND_REQUIRED}")
  set(_vtk_module_find_package_fail_if_not_found ON)
endif ()

if (_vtk_module_find_package_enabled)
  set(_vtk_module_find_package_required)
  if (_vtk_module_find_package_is_required)
    set(_vtk_module_find_package_required REQUIRED)
  endif ()

  find_package(TBB
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT TBB_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: TBB")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_CommonCore_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_CommonCore_NOT_FOUND_MESSAGE"
      "Failed to find the TBB package.")
  endif ()
  find_package(Threads
    
    
    
    ${_vtk_module_find_package_quiet}
    ${_vtk_module_find_package_required}
    COMPONENTS          
    OPTIONAL_COMPONENTS )
  if (NOT Threads_FOUND AND _vtk_module_find_package_fail_if_not_found)
    if (NOT ${CMAKE_FIND_PACKAGE_NAME}_FIND_QUIETLY)
      message(STATUS
        "Could not find the ${CMAKE_FIND_PACKAGE_NAME} package due to a "
        "missing dependency: Threads")
    endif ()
    set("${CMAKE_FIND_PACKAGE_NAME}_CommonCore_FOUND" 0)
    list(APPEND "${CMAKE_FIND_PACKAGE_NAME}_CommonCore_NOT_FOUND_MESSAGE"
      "Failed to find the Threads package.")
  endif ()
endif ()

unset(_vtk_module_find_package_fail_if_not_found)
unset(_vtk_module_find_package_enabled)
unset(_vtk_module_find_package_required)

unset(_vtk_module_find_package_components)
unset(_vtk_module_find_package_components_required)
unset(_vtk_module_find_package_quiet)
