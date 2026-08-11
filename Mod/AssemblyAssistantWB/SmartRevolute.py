# ***************************************************************************
# Smart Revolute Command
# ***************************************************************************

import os

import FreeCAD
import FreeCADGui

from PySide import QtGui


class SmartRevoluteCommand:

    def GetResources(self):

        icon = os.path.join(
            os.path.dirname(__file__),
            "Icons",
            "SmartRevolute.svg"
        )

        return {

            "Pixmap": icon,

            "MenuText": "Smart Revolute",

            "ToolTip": "Automatically create a revolute joint"

        }

    def Activated(self):

        QtGui.QMessageBox.information(

            None,

            "Assembly Assistant",

            "Smart Revolute prototype loaded successfully!"

        )

    def IsActive(self):

        return FreeCAD.ActiveDocument is not None