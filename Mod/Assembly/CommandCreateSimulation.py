# SPDX-License-Identifier: LGPL-2.1-or-later
# /**************************************************************************
#                                                                           *
#    Copyright (c) 2024 Ondsel <development@ondsel.com>                     *
#                                                                           *
#    This file is part of FreeCAD.                                          *
#                                                                           *
#    FreeCAD is free software: you can redistribute it and/or modify it     *
#    under the terms of the GNU Lesser General Public License as            *
#    published by the Free Software Foundation, either version 2.1 of the   *
#    License, or (at your option) any later version.                        *
#                                                                           *
#    FreeCAD is distributed in the hope that it will be useful, but         *
#    WITHOUT ANY WARRANTY; without even the implied warranty of             *
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU       *
#    Lesser General Public License for more details.                        *
#                                                                           *
#    You should have received a copy of the GNU Lesser General Public       *
#    License along with FreeCAD. If not, see                                *
#    <https://www.gnu.org/licenses/>.                                       *
#                                                                           *
# **************************************************************************/

import re
import os
import time
import FreeCAD as App

from pivy import coin
from Part import LineSegment, Compound

from PySide.QtCore import QT_TRANSLATE_NOOP

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtGui, QtWidgets
    from PySide.QtWidgets import (
        QPushButton,
        QMenu,
        QDialog,
        QComboBox,
        QLineEdit,
        QGridLayout,
        QLabel,
        QDialogButtonBox,
    )
    from PySide.QtCore import Qt, QPoint
    from PySide.QtGui import QCursor, QIcon, QGuiApplication

import UtilsAssembly
import Preferences

translate = App.Qt.translate

__title__ = "Assembly Command Create Simulation"
__author__ = "Ondsel"
__url__ = "https://www.freecad.org"


class CommandCreateSimulation:
    def __init__(self):
        pass

    def GetResources(self):
        return {
            "Pixmap": "Assembly_CreateSimulation",
            "MenuText": QT_TRANSLATE_NOOP("Assembly_CreateSimulation", "Simulation"),
            "Accel": "V",
            "ToolTip": QT_TRANSLATE_NOOP(
                "Assembly_CreateSimulation",
                "Creates a new simulation of the current assembly",
            ),
            "CmdType": "ForEdit",
        }

    def IsActive(self):
        if not UtilsAssembly.isAssemblyCommandActive():
            return False

        assembly = UtilsAssembly.activeAssembly()
        joint_types = ["Revolute", "Slider", "Cylindrical"]
        joints = UtilsAssembly.getJointsOfType(assembly, joint_types)
        return len(joints) > 0

    def Activated(self):

        assembly = UtilsAssembly.activeAssembly()
        if not assembly:
            return

        reply = QtWidgets.QMessageBox.question(
            None,
            "Assembly Assistant",
            "🤖 Assembly Assistant\n\n"
            "I will help you prepare this assembly for simulation.\n\n"
            "The first step is to identify the driving axis.\n\n"
            "Continue?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Yes,
        )

        if reply != QtWidgets.QMessageBox.Yes:
            return

        self.panel = TaskAssemblyCreateSimulation()

        dialog = Gui.Control.showDialog(self.panel)

        if dialog is not None:
            dialog.setAutoCloseOnDeletedDocument(True)
            dialog.setDocumentName(App.ActiveDocument.Name)


######### Simulation Object ###########
class Simulation:
    def __init__(self, feaPy):
        feaPy.Proxy = self
        feaPy.addExtension("App::GroupExtensionPython")

        if not hasattr(feaPy, "aTimeStart"):
            feaPy.addProperty(
                "App::PropertyTime",
                "aTimeStart",
                "Simulation",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Simulation start time.",
                ),
                locked=True,
            )

        if not hasattr(feaPy, "bTimeEnd"):
            feaPy.addProperty(
                "App::PropertyTime",
                "bTimeEnd",
                "Simulation",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Simulation end time.",
                ),
                locked=True,
            )

        if not hasattr(feaPy, "cTimeStepOutput"):
            feaPy.addProperty(
                "App::PropertyTime",
                "cTimeStepOutput",
                "Simulation",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Simulation time step for output.",
                ),
                locked=True,
            )

        if not hasattr(feaPy, "fGlobalErrorTolerance"):
            feaPy.addProperty(
                "App::PropertyFloat",
                "fGlobalErrorTolerance",
                "Simulation",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Integration global error tolerance.",
                ),
                locked=True,
            )

        if not hasattr(feaPy, "jFramesPerSecond"):
            feaPy.addProperty(
                "App::PropertyInteger",
                "jFramesPerSecond",
                "Simulation",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Frames Per Second.",
                ),
                locked=True,
            )

        feaPy.aTimeStart = 0.0
        feaPy.bTimeEnd = 1.0
        feaPy.cTimeStepOutput = 1.0e-2
        feaPy.fGlobalErrorTolerance = 1.0e-6
        feaPy.jFramesPerSecond = 30

        self.motionsChangedCallback = None

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def onChanged(self, feaPy, prop):
        if prop == "Group" and hasattr(self, "motionsChangedCallback"):
            if self.motionsChangedCallback is not None:
                self.motionsChangedCallback()

    def setMotionsChangedCallback(self, callback):
        self.motionsChangedCallback = callback

    def execute(self, feaPy):
        """Do something when doing a recomputation, this method is mandatory"""
        pass

    def getAssembly(self, feaPy):
        assert feaPy.isDerivedFrom("App::FeaturePython"), "Type error"
        for obj in feaPy.InList:
            if obj.isDerivedFrom("Assembly::AssemblyObject"):
                return obj
        return None


class ViewProviderSimulation:
    def __init__(self, vpDoc):
        vpDoc.Proxy = self
        self.Object = vpDoc.Object
        self.setProperties(vpDoc)

    def setProperties(self, vpDoc):
        if not hasattr(vpDoc, "Decimals"):
            vpDoc.addProperty(
                "App::PropertyInteger",
                "Decimals",
                "Space",
                QT_TRANSLATE_NOOP(
                    "App::Property", "The number of decimals to use for calculated texts"
                ),
                locked=True,
            )
            vpDoc.Decimals = 9

    def attach(self, vpDoc):
        """Setup the scene sub-graph of the view provider, this method is mandatory"""
        self.app_obj = vpDoc.Object

        self.display_mode = coin.SoType.fromName("SoFCSelection").createInstance()

        vpDoc.addDisplayMode(self.display_mode, "Wireframe")

    def updateData(self, feaPy, prop):
        """If a property of the handled feature has changed we have the chance to handle this here"""
        pass

    def getDisplayModes(self, vpDoc):
        """Return a list of display modes."""
        return ["Wireframe"]

    def getDefaultDisplayMode(self):
        """Return the name of the default display mode. It must be defined in getDisplayModes."""
        return "Wireframe"

    def onChanged(self, vpDoc, prop):
        """Here we can do something when a single property got changed"""
        pass

    def getIcon(self):
        return ":/icons/Assembly_CreateSimulation.svg"

    def dumps(self):
        """When saving the document this object gets stored using Python's json module.\
                Since we have some un-serializable parts here -- the Coin stuff -- we must define this method\
                to return a tuple of all serializable objects or None."""
        return None

    def loads(self, state):
        """When restoring the serialized object from document we have the chance to set some internals here.\
                Since no data were serialized nothing needs to be done here."""
        return None

    def claimChildren(self):
        return self.app_obj.Group

    def doubleClicked(self, vpDoc):
        task = Gui.Control.activeTaskDialog()
        if task:
            task.reject()

        assembly = vpDoc.Object.Proxy.getAssembly(vpDoc.Object)

        if assembly is None:
            return False

        if UtilsAssembly.activeAssembly() != assembly:
            Gui.ActiveDocument.setEdit(assembly)

        panel = TaskAssemblyCreateSimulation(vpDoc.Object)
        dialog = Gui.Control.showDialog(panel)
        if dialog is not None:
            dialog.setAutoCloseOnDeletedDocument(True)
            dialog.setDocumentName(App.ActiveDocument.Name)

        return True

    def onDelete(self, vobj, subelements):
        for obj in self.claimChildren():
            obj.Document.removeObject(obj.Name)
        return True


########### Motion Object #############
MotionTypes = [
    "Angular",
    "Linear",
]


class Motion:
    def __init__(self, feaPy, motionType=MotionTypes[0], joint=None, formula=""):
        feaPy.Proxy = self

        self.createProperties(feaPy)

        feaPy.MotionType = MotionTypes  # sets the list
        feaPy.MotionType = motionType  # set the initial value
        feaPy.Joint = joint
        feaPy.Formula = formula

    def onDocumentRestored(self, feaPy):
        self.createProperties(feaPy)

    def createProperties(self, feaPy):
        if not hasattr(feaPy, "Joint"):
            feaPy.addProperty(
                "App::PropertyXLinkSubHidden",
                "Joint",
                "Motion",
                QT_TRANSLATE_NOOP("App::Property", "The joint that is moved by the motion"),
                locked=True,
            )

        if not hasattr(feaPy, "Formula"):
            feaPy.addProperty(
                "App::PropertyString",
                "Formula",
                "Motion",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "This is the formula of the motion. For example '1.0*time'.",
                ),
                locked=True,
            )

        if not hasattr(feaPy, "MotionType"):
            feaPy.addProperty(
                "App::PropertyEnumeration",
                "MotionType",
                "Motion",
                QT_TRANSLATE_NOOP("App::Property", "The type of the motion"),
                locked=True,
            )

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def onChanged(self, feaPy, prop):
        pass

    def execute(self, feaPy):
        """Do something when doing a recomputation, this method is mandatory"""
        pass

    def getSimulation(self, feaPy):
        for obj in feaPy.InList:
            if hasattr(obj, "Proxy"):
                if hasattr(obj.Proxy, "setMotionsChangedCallback"):
                    return obj
        return None

    def getAssembly(self, feaPy):
        simulation = self.getSimulation(feaPy)
        if simulation is not None:
            return simulation.Proxy.getAssembly(simulation)
        return None


class ViewProviderMotion:
    def __init__(self, vp):
        vp.Proxy = self
        self.updateLabel()

    def attach(self, vpDoc):
        """Setup the scene sub-graph of the view provider, this method is mandatory"""
        self.app_obj = vpDoc.Object

        self.display_mode = coin.SoType.fromName("SoFCSelection").createInstance()

        vpDoc.addDisplayMode(self.display_mode, "Wireframe")

    def updateData(self, feaPy, prop):
        """If a property of the handled feature has changed we have the chance to handle this here"""
        pass

    def getDisplayModes(self, vpDoc):
        """Return a list of display modes."""
        return ["Wireframe"]

    def getDefaultDisplayMode(self):
        """Return the name of the default display mode. It must be defined in getDisplayModes."""
        return "Wireframe"

    def onChanged(self, vpDoc, prop):
        """Here we can do something when a single property got changed"""
        # App.Console.PrintMessage("Change property: " + str(prop) + "\n")
        pass

    def getIcon(self):
        if self.app_obj.MotionType == "Angular":
            return ":/icons/button_rotate.svg"

        return ":/icons/button_right.svg"

    def dumps(self):
        """When saving the document this object gets stored using Python's json module.\
                Since we have some un-serializable parts here -- the Coin stuff -- we must define this method\
                to return a tuple of all serializable objects or None."""
        return None

    def loads(self, state):
        """When restoring the serialized object from document we have the chance to set some internals here.\
                Since no data were serialized nothing needs to be done here."""
        return None

    def doubleClicked(self, vpDoc):
        self.openEditDialog()

    def openEditDialog(self):
        assembly = self.getAssembly()

        if assembly is None:
            return False

        joint = None
        if self.app_obj.Joint is not None:
            joint = self.app_obj.Joint[0]

        dialog = MotionEditDialog(assembly, self.app_obj.MotionType, joint, self.app_obj.Formula)
        if dialog.exec_():
            self.app_obj.MotionType = dialog.motionType
            self.app_obj.Joint = dialog.joint
            self.app_obj.Formula = dialog.formula

            self.updateLabel()

    def updateLabel(self):
        if self.app_obj.Joint is None:
            return

        typeStr = "Linear" if self.app_obj.MotionType == "Linear" else "Angular"

        self.app_obj.Label = "{label} ({type_})".format(
            label=self.app_obj.Joint[0].Label, type_=translate("Assembly", typeStr)
        )

    def getAssembly(self):
        assembly = self.app_obj.Proxy.getAssembly(self.app_obj)

        if assembly is None:
            return None

        if UtilsAssembly.activeAssembly() != assembly:
            Gui.ActiveDocument.setEdit(assembly)

        return assembly


class MotionEditDialog:
    def __init__(self, assembly, motionType=MotionTypes[0], joint=None, formula="5*time"):
        self.assembly = assembly
        self.motionType = motionType
        self.joint = joint
        self.formula = formula

        # Create a non-modal, frameless dialog
        self.dialog = QDialog()
        self.dialog.setWindowFlags(Qt.Popup)
        self.initialPos = QCursor.pos()
        self.dialog.setMinimumSize(500, 200)  # Set a reasonable minimum size

        # Create the joints combobox
        self.joint_combo = QComboBox(self.dialog)
        self.setup_joint_combo()

        # Create the motion type combobox
        self.motion_type_combo = QComboBox(self.dialog)
        self.setup_motiontype_combo()

        def on_motion_type_changed(text):
            self.motionType = text

        self.motion_type_combo.currentTextChanged.connect(on_motion_type_changed)

        def on_joint_changed(index):
            self.joint = self.joint_combo.itemData(index)
            self.setup_motiontype_combo()  # Refresh the motion combo box based on the new joint type

        self.joint_combo.currentIndexChanged.connect(on_joint_changed)

        # Create the line edit for the formula
        formula_edit = QLineEdit(self.dialog)
        formula_edit.setText(self.formula)
        formula_edit.setPlaceholderText(translate("Assembly", "Enter your formula..."))

        # Connect the line edit to update the Formula property
        def on_formula_changed(text):
            self.formula = text

        formula_edit.textChanged.connect(on_formula_changed)

        self.setupHelpSection()

        # Create Ok and Cancel buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self.dialog
        )
        button_box.accepted.connect(self.dialog.accept)
        button_box.rejected.connect(self.dialog.reject)

        # Set up the layout of the dialog
        layout = QGridLayout(self.dialog)

        # Add labels and widgets to the layout
        layout.addWidget(QLabel("Joint"), 0, 0)
        layout.addWidget(self.joint_combo, 0, 1)

        layout.addWidget(QLabel("Motion Type"), 1, 0)
        layout.addWidget(self.motion_type_combo, 1, 1)

        layout.addWidget(QLabel("Formula"), 2, 0)
        layout.addWidget(formula_edit, 2, 1)

        # Add the help label above the buttons
        layout.addWidget(self.help_label0, 3, 0, 1, 2)
        layout.addWidget(self.help_label1, 4, 0, 1, 2)
        layout.addWidget(self.help_label2, 5, 0, 1, 2)
        layout.addWidget(self.help_label3, 6, 0, 1, 2)
        layout.addWidget(self.help_label4, 7, 0, 1, 2)
        layout.addWidget(self.help_label5, 8, 0, 1, 2)
        layout.addWidget(self.help_label6, 9, 0, 1, 2)
        layout.addWidget(self.help_label7, 10, 0, 1, 2)
        # Add the help button and button box in the next row
        layout.addWidget(self.help_button, 11, 0)

        layout.addWidget(button_box, 11, 1)

        self.positionDialog()

    def setupHelpSection(self):

        # Create the help QLabels and set them to be initially hidden
        self.help_label0 = QLabel(
            translate(
                "Assembly",
                "In capital are variables that you need to replace with actual values. More details about each example in its tooltip.",
            ),
            self.dialog,
        )
        self.help_label1 = QLabel(translate("Assembly", " - Linear: C + VEL*time"), self.dialog)
        self.help_label2 = QLabel(
            translate("Assembly", " - Quadratic: C + VEL*time + ACC*time^2"), self.dialog
        )
        self.help_label3 = QLabel(
            translate("Assembly", " - Harmonic: C + AMP*sin(VEL*time - PHASE)"), self.dialog
        )
        self.help_label4 = QLabel(
            translate("Assembly", " - Exponential: C*exp(time/TIMEC)"), self.dialog
        )
        self.help_label5 = QLabel(
            translate(
                "Assembly",
                " - Smooth Step: L1 + (L2 - L1)*((1/2) + (1/pi)*arctan(SLOPE*(time - T0)))",
            ),
            self.dialog,
        )
        self.help_label6 = QLabel(
            translate(
                "Assembly",
                " - Smooth Square Impulse: (H/pi)*(arctan(SLOPE*(time - T1)) - arctan(SLOPE*(time - T2)))",
            ),
            self.dialog,
        )
        self.help_label7 = QLabel(
            translate(
                "Assembly",
                " - Smooth Ramp Top Impulse: ((1/pi)*(arctan(1000*(time - T1)) - arctan(1000*(time - T2))))*(((H2 - H1)/(T2 - T1))*(time - T1) + H1)",
            ),
            self.dialog,
        )

        self.help_label1.setToolTip(
            translate(
                "Assembly",
                """C is a constant offset.
VEL is a velocity or slope or gradient of the straight line.""",
            )
        )
        self.help_label2.setToolTip(
            translate(
                "Assembly",
                """C is a constant offset.
VEL is the velocity or slope or gradient of the straight line.
ACC is the acceleration or coefficient of the second order. The function is a parabola.""",
            )
        )
        self.help_label3.setToolTip(
            translate(
                "Assembly",
                """C is a constant offset.
AMP is the amplitude of the sine wave.
VEL is the angular velocity in radians per second.
PHASE is the phase of the sine wave.""",
            )
        )
        self.help_label4.setToolTip(
            translate(
                "Assembly",
                """C is a constant.
TIMEC is the time constant of the exponential function.""",
            )
        )
        self.help_label5.setToolTip(
            translate(
                "Assembly",
                """L1 is step level before time = T0.
L2 is step level after time = T0.
SLOPE defines the steepness of the transition between L1 and L2 about time = T0. Higher values gives sharper cornered steps. SLOPE = 1000 or greater are suitable.""",
            )
        )
        self.help_label6.setToolTip(
            translate(
                "Assembly",
                """H is the height of the impulse.
T1 is the start of the impulse.
T2 is the end of the impulse.
SLOPE defines the steepness of the transition between 0 and H about time = T1 and T2. Higher values gives sharper cornered impulses. SLOPE = 1000 or greater are suitable.""",
            )
        )
        self.help_label7.setToolTip(
            translate(
                "Assembly",
                """This is similar to the square impulse but the top has a sloping ramp. It is good for building a smooth piecewise linear function by adding a series of these.
T1 is the start of the impulse.
T2 is the end of the impulse.
H1 is the height at T1 at the beginning of the ramp.
H2 is the height at T2 at the end of the ramp.
SLOPE defines the steepness of the transition between 0 and H1 and H2 to 0 about time = T1 and T2 respectively. Higher values gives sharper cornered impulses. SLOPE = 1000 or greater are suitable.""",
            )
        )

        self.help_label0.setWordWrap(True)
        self.help_label1.setWordWrap(True)
        self.help_label2.setWordWrap(True)
        self.help_label3.setWordWrap(True)
        self.help_label4.setWordWrap(True)
        self.help_label5.setWordWrap(True)
        self.help_label6.setWordWrap(True)
        self.help_label7.setWordWrap(True)

        width = 1000
        self.help_label0.setFixedWidth(width)
        self.help_label1.setFixedWidth(width)
        self.help_label2.setFixedWidth(width)
        self.help_label3.setFixedWidth(width)
        self.help_label4.setFixedWidth(width)
        self.help_label5.setFixedWidth(width)
        self.help_label6.setFixedWidth(width)
        self.help_label7.setFixedWidth(width)

        self.help_label0.setVisible(False)
        self.help_label1.setVisible(False)
        self.help_label2.setVisible(False)
        self.help_label3.setVisible(False)
        self.help_label4.setVisible(False)
        self.help_label5.setVisible(False)
        self.help_label6.setVisible(False)
        self.help_label7.setVisible(False)

        self.help_label1.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.help_label2.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.help_label3.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.help_label4.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.help_label5.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.help_label6.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.help_label7.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # Create the Help button
        self.help_button = QPushButton(translate("Assembly", "Help"), self.dialog)

        # Slot to toggle help visibility and button text
        def toggle_help():
            show = not self.help_label1.isVisible()
            self.help_label0.setVisible(show)
            self.help_label1.setVisible(show)
            self.help_label2.setVisible(show)
            self.help_label3.setVisible(show)
            self.help_label4.setVisible(show)
            self.help_label5.setVisible(show)
            self.help_label6.setVisible(show)
            self.help_label7.setVisible(show)

            if show:
                self.help_button.setText(translate("Assembly", "Hide help"))
            else:
                self.help_button.setText(translate("Assembly", "Help"))

            self.positionDialog()

        self.help_button.clicked.connect(toggle_help)

    def positionDialog(self):
        self.dialog.adjustSize()

        # Get the screen where the mouse is located
        screen = QGuiApplication.screenAt(self.initialPos)
        screen_geometry = (
            screen.availableGeometry()
            if screen
            else QApplication.primaryScreen().availableGeometry()
        )

        # Calculate the position of the dialog to ensure it stays within the screen
        dialog_position = self.initialPos

        # Adjust position to keep the dialog within the screen bounds
        if dialog_position.x() + self.dialog.width() > screen_geometry.right():
            dialog_position.setX(screen_geometry.right() - self.dialog.width())
        if dialog_position.y() + self.dialog.height() > screen_geometry.bottom():
            dialog_position.setY(screen_geometry.bottom() - self.dialog.height())

        # Ensure the dialog does not go above or to the left of the screen
        if dialog_position.x() < screen_geometry.left():
            dialog_position.setX(screen_geometry.left())
        if dialog_position.y() < screen_geometry.top():
            dialog_position.setY(screen_geometry.top())

        # Move the dialog to the final position
        self.dialog.move(dialog_position)

    def setup_joint_combo(self):
        # Function to set up the joint combo box based on the selected motion type

        self.joint_combo.clear()  # Clear existing items

        jointTypes = ["Revolute", "Slider", "Cylindrical"]

        joints = UtilsAssembly.getJointsOfType(self.assembly, jointTypes)

        # Add joints to the combo box with labels and icons
        for joint in joints:
            joint_label = joint.Label
            joint_icon = QIcon(joint.ViewObject.Icon)
            self.joint_combo.addItem(joint_icon, joint_label, userData=joint)

        # Set the current value based on the object's Joint property
        if self.joint in joints:
            self.joint_combo.setCurrentText(self.joint.Label)
        elif len(joints) > 0:
            self.joint = joints[0]

    def setup_motiontype_combo(self):
        self.motion_type_combo.clear()  # Clear existing items

        if self.joint is None:
            return

        if self.joint.JointType == "Revolute":
            types = ["Angular"]
        elif self.joint.JointType == "Slider":
            types = ["Linear"]
        else:
            types = ["Angular", "Linear"]

        self.motion_type_combo.addItems(types)

        # Set current value based on the object's MotionType
        if self.motionType in types:
            self.motion_type_combo.setCurrentText(self.motionType)
        else:
            # self.motionType is no longer available, so we reset it to first entry
            self.motionType = types[0]

    def exec_(self):
        return self.dialog.exec()


######### Create Simulation Task ###########
class TaskAssemblyCreateSimulation(QtCore.QObject):
    def __init__(self, simFeaturePy=None):
        self.currentStep = 0
        super().__init__()
        self.assembly = UtilsAssembly.activeAssembly()

        self.initialPlcs = UtilsAssembly.saveAssemblyPartsPlacements(self.assembly)

        self.doc = self.assembly.Document
        self.gui_doc = Gui.getDocument(self.doc)

        self.view = self.gui_doc.activeView()

        if not self.assembly or not self.view or not self.doc:
            return

        self.runKinematicsTimer = QtCore.QTimer()
        self.runKinematicsTimer.setSingleShot(True)
        self.runKinematicsTimer.timeout.connect(self.displayLastFrame)

        self.animationTimer = QtCore.QTimer()
        self.animationTimer.setInterval(50)  # ms
        self.animationTimer.timeout.connect(self.playAnimation)

        self.form = Gui.PySideUic.loadUi(":/panels/TaskAssemblyCreateSimulation.ui")

        layout = self.form.verticalLayout_2

        # --------------------------------------------------
        # Simulation Assistant
        # --------------------------------------------------

        assistantGroup = QtWidgets.QGroupBox("🤖 Simulation Assistant")

        self.assistantLayout = QtWidgets.QVBoxLayout()

        self.assistantTitle = QtWidgets.QLabel(
            "<h2>🤖 Simulation Assistant</h2>"
        )

        self.assistantLayout.addWidget(self.assistantTitle)

        self.assistantStatus = QtWidgets.QLabel(
            "<b>Step 1 of 6</b><br><br>"
            "Let's identify the driving axis.<br><br>"
            "Press <b>Highlight Axis</b> to begin."
        )

        self.assistantStatus.setWordWrap(True)

        self.assistantLayout.addWidget(self.assistantStatus)

        self.assistantButtonYes = QtWidgets.QPushButton("✓ Yes")
        self.assistantButtonNo = QtWidgets.QPushButton("↻ Recalculate")

        self.assistantButtonYes.hide()
        self.assistantButtonNo.hide()

        self.assistantLayout.addWidget(self.assistantButtonYes)
        self.assistantLayout.addWidget(self.assistantButtonNo)

        self.highlightAxisButton = QtWidgets.QPushButton("Highlight Axis")
        self.RecheckButton = QtWidgets.QPushButton("Recheck assembly")

        self.axisYesButton = QtWidgets.QPushButton("✓ Yes")

        self.axisChooseButton = QtWidgets.QPushButton("Choose Another")

        self.highlightAxisButton.clicked.connect(
            self.onAssistantButton
        )

        self.RecheckButton.clicked.connect(
                    self.RecheckAssembly
                )

        self.backButton = QtWidgets.QPushButton("⬅ Back")
        self.backButton.clicked.connect(self.goBackStep)
        self.backButton.setEnabled(False)  # Disabled at Step 0

        self.assistantLayout.addWidget(self.highlightAxisButton)
        self.assistantLayout.addWidget(self.RecheckButton)
        self.assistantLayout.addWidget(self.backButton)

        assistantGroup.setLayout(self.assistantLayout)

        # Put the assistant at the TOP of the panel
        layout.insertWidget(0, assistantGroup)

        self.analyseAssembly()

        self.form.motionList.installEventFilter(self)
        self.setSpinboxPrecision(self.form.TimeStartSpinBox, 9)
        self.setSpinboxPrecision(self.form.TimeEndSpinBox, 9)
        self.setSpinboxPrecision(self.form.TimeStepOutputSpinBox, 9)
        self.setSpinboxPrecision(self.form.GlobalErrorToleranceSpinBox, 9, App.Units.Length)
        self.form.motionList.itemDoubleClicked.connect(self.onItemDoubleClicked)
        self.form.TimeStartSpinBox.valueChanged.connect(self.onTimeStartChanged)
        self.form.TimeEndSpinBox.valueChanged.connect(self.onTimeEndChanged)
        self.form.TimeStepOutputSpinBox.valueChanged.connect(self.onTimeStepOutputChanged)
        self.form.GlobalErrorToleranceSpinBox.valueChanged.connect(
            self.onGlobalErrorToleranceChanged
        )
        self.form.RunKinematicsButton.clicked.connect(self.runKinematics)
        self.form.frameSlider.valueChanged.connect(self.onFrameChanged)
        self.form.FramesPerSecondSpinBox.valueChanged.connect(self.onFramesPerSecondChanged)
        self.form.PlayBackwardButton.clicked.connect(self.animationTimerStartBackward)
        self.form.PlayForwardButton.clicked.connect(self.animationTimerStartForward)
        self.form.StepBackwardButton.clicked.connect(self.stepBackward)
        self.form.StepForwardButton.clicked.connect(self.stepForward)
        self.form.StopButton.clicked.connect(self.stopAnimation)
        self.form.AddButton.clicked.connect(self.addMotionClicked)
        self.form.RemoveButton.clicked.connect(self.deleteSelectedMotions)
        self.form.groupBox_player.hide()

        if simFeaturePy:
            self.simFeaturePy = simFeaturePy
            App.setActiveTransaction("Edit " + simFeaturePy.Label + " Simulation")
            self.onMotionsChanged()
        else:
            App.setActiveTransaction("Create Simulation")
            self.createSimulationObject()

        self.setUiInitialValues()

        self.simFeaturePy.Proxy.setMotionsChangedCallback(self.onMotionsChanged)

        self.currentFrm = 1
        self.startFrm = 1
        self.endFrm = 100
        self.fps = 30
        self.deltaTime = 1.0 / self.fps
        self.startTime = time.time()
        self.index = 0

    def analyseAssembly(self):
        self.currentStep = 0

        bodies = []
        revolute = 0
        fixed = 0
        slider = 0

        # Reset detected bodies
        self.groundedBody = None
        self.movingBody = None

        App.Console.PrintMessage("\n=== Starting Assembly Analysis ===\n")

        # --------------------------------------------------
        # 1. Collect all components in active assembly
        # --------------------------------------------------
        for obj in self.doc.Objects:
            is_component = (
                obj.isDerivedFrom("PartDesign::Body") or 
                obj.isDerivedFrom("App::Part") or 
                obj.isDerivedFrom("App::Link")
            )

            if is_component and (
                (hasattr(obj, "getParentGeoFeatureGroup") and obj.getParentGeoFeatureGroup() == self.assembly) or 
                (hasattr(self.assembly, "Group") and obj in self.assembly.Group)
            ):
                bodies.append(obj)
                App.Console.PrintMessage(f"Found Component: {obj.Label} ({obj.Name})\n")

        # --------------------------------------------------
        # 2. Extract Grounded Objects and count Joints
        # --------------------------------------------------
        # DEBUG: Print all objects and their properties
        App.Console.PrintMessage("\n=== DEBUG: Searching for Joints ===\n")
        for obj in self.doc.Objects:
            # Print basic info
            App.Console.PrintMessage(f"Object: {obj.Name} ({obj.Label})")
            App.Console.PrintMessage(f"  TypeId: {obj.TypeId}")
            
            # Print all properties that might relate to joints
            for prop in dir(obj):
                if "Joint" in prop or "joint" in prop or "Type" in prop:
                    try:
                        val = getattr(obj, prop)
                        App.Console.PrintMessage(f"  {prop}: {val}")
                    except:
                        pass
            App.Console.PrintMessage("---")
        
        grounded_objects = set()

        for obj in self.doc.Objects:
            is_grounded_joint = (
                "Grounded" in obj.Name or 
                "Grounded" in str(getattr(obj, "TypeId", "")) or
                getattr(obj, "JointType", "") in ["Grounded", "Fixed"]
            )

            if is_grounded_joint:
                for prop in ["ObjectToGround", "DataObjectToGround", "Target"]:
                    target = getattr(obj, prop, None)
                    if target:
                        grounded_objects.add(target)

                ref1 = getattr(obj, "Reference1", None)
                if ref1:
                    if isinstance(ref1, (list, tuple)) and len(ref1) > 0:
                        elem = ref1[0]
                        if isinstance(elem, (list, tuple)) and len(elem) > 0:
                            grounded_objects.add(elem[0])
                        else:
                            grounded_objects.add(elem)

            if hasattr(obj, "JointType"):
                if obj.JointType == "Revolute":
                    revolute += 1
                elif obj.JointType == "Fixed":
                    fixed += 1
                elif obj.JointType == "Slider":
                    slider += 1

        # --------------------------------------------------
        # 3. Match Grounded Objects to Assembly Components
        # --------------------------------------------------
        grounded_count = 0

        for body in bodies:
            linked_obj = getattr(body, "LinkedObject", None)
            
            if body in grounded_objects or (linked_obj and linked_obj in grounded_objects):
                grounded_count += 1
                if self.groundedBody is None:
                    self.groundedBody = body

        for body in bodies:
            if body != self.groundedBody:
                self.movingBody = body
                break

        moving_count = max(0, len(bodies) - grounded_count)

        # Clean Console Summary
        App.Console.PrintMessage(f"Total Bodies: {len(bodies)}\n")
        App.Console.PrintMessage(f"Grounded Body: {self.groundedBody.Label if self.groundedBody else 'None'}\n")
        App.Console.PrintMessage(f"Moving Body: {self.movingBody.Label if self.movingBody else 'None'}\n")
        App.Console.PrintMessage("=== Analysis Complete ===\n\n")

        # --------------------------------------------------
        # 4. Update Assistant UI
        # --------------------------------------------------
        self.assistantStep(
            0,
            6,
            "Assembly Analysis",
            f"""
            I analysed your assembly.<br><br>

            <b>Bodies</b><br>
            • Total Bodies : {len(bodies)}<br>
            • Grounded : {grounded_count}<br>
            • Moving : {moving_count}<br><br>

            <b>Joints</b><br>
            • Revolute : {revolute}<br>
            • Fixed : {fixed}<br>
            • Slider : {slider}<br><br>

            Does this look correct?
            """
        )

        self.highlightAxisButton.setText("Confirm Assembly")
        self.RecheckButton.setText("Recheck assembly")
        self.updateBackButtonState()

    def RecheckAssembly(self):
        # If the assembly analysis is not correct
        # Re-analyse the assembly and reset the assistant
        
        if self.RecheckButton.text() == "Recheck assembly":
            
            self.analyseAssembly()
            return
        
        # Re-analyse the assembly and rehighlight the driving axis
        
        if self.RecheckButton.text() == "Recheck axis":
                    
            self.highlightDrivingAxis()
            return


    def onAssistantButton(self):

        # ------------------------------------------
        # Step 0: Assembly analysis confirmed
        # ------------------------------------------

        if self.highlightAxisButton.text() == "Confirm Assembly":

            self.highlightDrivingAxis()
            return

        # ------------------------------------------
        # Step 1/2: Driving axis highlighted
        # ------------------------------------------

        if self.highlightAxisButton.text() == "Confirm Axis":

            self.showInitialBodyState()
            return
    
    def assistantStep(self, step, total, title, text):

        self.assistantTitle.setText(
            f"<h2>🤖 Simulation Assistant</h2>"
            f"<h3>Step {step} of {total}</h3>"
        )

        self.assistantStatus.setText(
            f"<b>{title}</b><br><br>{text}"
        )

        QtWidgets.QApplication.processEvents()

    def highlightDrivingAxis(self):
        self.currentStep = 1
        import pivy.coin as coin
        
        App.Console.PrintMessage("\n=== Highlight Driving Axis ===\n")

        # ------------------------------------------
        # Remove previous highlight
        # ------------------------------------------
        try:
            if hasattr(self, "axisGraphic"):
                self.view.getSceneGraph().removeChild(self.axisGraphic)
        except Exception:
            pass

        root = self.view.getSceneGraph()

        # ------------------------------------------
        # Define joint handlers
        # ------------------------------------------
        
        joint_handlers = {
            "Revolute": self._extract_revolute_axis,
            "Slider": self._extract_slider_axis,
            "Cylindrical": self._extract_cylindrical_axis,
            "Fixed": self._extract_fixed_axis,
        }

        # ------------------------------------------
        # Find the first joint
        # ------------------------------------------
        
        found_joint = None
        found_type = None
        axis = None
        origin = None

        for obj in self.doc.Objects:
            # Try to get joint type - FIXED: handle None
            joint_type = None
            for prop in ["JointType", "Type", "JointTypeId"]:
                if hasattr(obj, prop):
                    val = getattr(obj, prop)
                    if val is not None:
                        joint_type = str(val)
                    break
            
            # If still None, try checking name and references
            if not joint_type:
                if "Joint" in obj.Name or "Joint" in obj.Label:
                    if hasattr(obj, "Reference1") or hasattr(obj, "Reference2"):
                        # Try to determine type from other properties
                        if hasattr(obj, "JointType"):
                            joint_type = str(obj.JointType)
                        else:
                            joint_type = "Unknown"
                else:
                    continue
            
            # Skip if still None
            if joint_type is None:
                continue
            
            # Debug: Print what we found
            App.Console.PrintMessage(f"Checking object: {obj.Name} - Type: {joint_type}\n")
            
            # Find matching handler - FIXED: handle None safely
            handler = None
            matched_type = None
            for known_type in joint_handlers:
                # Safely check if joint_type contains known_type or vice versa
                if joint_type is not None and known_type is not None:
                    if known_type.lower() in joint_type.lower() or joint_type.lower() in known_type.lower():
                        handler = joint_handlers[known_type]
                        matched_type = known_type
                        break
            
            if handler is None:
                App.Console.PrintMessage(f"Skipping unknown joint: {obj.Name} (Type: {joint_type})\n")
                continue
            
            # Extract axis and origin using the handler
            try:
                axis, origin = handler(obj)
                if axis is not None and origin is not None:
                    found_joint = obj
                    found_type = matched_type
                    break
            except Exception as e:
                App.Console.PrintError(f"Error extracting from {obj.Name}: {e}\n")
                continue

        # ------------------------------------------
        # If no joint found, show error
        # ------------------------------------------
        
        if found_joint is None:
            self.assistantStep(
                1,
                6,
                "⚠️ No Driving Joint Found",
                """
                <b>⚠️ No detectable joint found.</b><br><br>
                
                I could not find a revolute, slider, or cylindrical joint.<br><br>
                
                Please ensure:<br>
                • You have created at least one joint<br>
                • The joint type is supported<br><br>
                
                <b>Supported types:</b> Revolute, Slider, Cylindrical<br><br>
                
                Click <b>"Recheck"</b> to scan again.
                """
            )
            self.RecheckButton.setText("Recheck axis")
            self.RecheckButton.clicked.disconnect()
            self.RecheckButton.clicked.connect(self.recheckJoints)
            self.RecheckButton.show()
            return

        # ------------------------------------------
        # Normalize axis
        # ------------------------------------------
        
        if axis.Length > 0:
            axis.normalize()
        else:
            axis = App.Vector(0, 0, 1)

        App.Console.PrintMessage(f"FOUND JOINT: {found_joint.Name}\n")
        App.Console.PrintMessage(f"Type: {found_type}\n")
        App.Console.PrintMessage(f"Origin: {origin}\n")
        App.Console.PrintMessage(f"Axis: {axis}\n")

        # ------------------------------------------
        # Create the axis line in 3D view
        # ------------------------------------------
        
        length = 300
        p1 = origin - axis * (length / 2)
        p2 = origin + axis * (length / 2)

        sep = coin.SoSeparator()

        # Color based on joint type
        colors = {
            "Revolute": (0.0, 0.45, 1.0),    # Blue
            "Slider": (0.0, 1.0, 0.45),      # Green
            "Cylindrical": (1.0, 0.45, 0.0), # Orange
            "Fixed": (1.0, 0.0, 0.0),        # Red
        }
        color = colors.get(found_type, (0.0, 0.45, 1.0))

        material = coin.SoMaterial()
        material.diffuseColor = color
        material.emissiveColor = color

        drawStyle = coin.SoDrawStyle()
        drawStyle.lineWidth = 5

        coords = coin.SoCoordinate3()
        coords.point.setValues(
            0,
            2,
            [
                (p1.x, p1.y, p1.z),
                (p2.x, p2.y, p2.z),
            ],
        )

        line = coin.SoLineSet()
        sep.addChild(material)
        sep.addChild(drawStyle)
        sep.addChild(coords)
        sep.addChild(line)

        root.addChild(sep)
        self.axisGraphic = sep

        # ------------------------------------------
        # Store joint info for later use
        # ------------------------------------------
        
        self.currentJoint = found_joint
        self.currentJointType = found_type
        self.currentAxis = axis
        self.currentOrigin = origin

        # ------------------------------------------
        # Update Assistant
        # ------------------------------------------
        
        joint_type_display = {
            "Revolute": "Revolute Joint (Rotation Axis)",
            "Slider": "Slider Joint (Translation Direction)",
            "Cylindrical": "Cylindrical Joint (Combined Axis)",
            "Fixed": "Fixed Joint (No Motion)",
        }.get(found_type, "Driving Axis")

        self.assistantStep(
            1,
            6,
            f"{joint_type_display} Detected",
            f"""
            I have highlighted the detected axis.<br><br>
            
            <b>Joint Name:</b> {found_joint.Label}<br>
            <b>Joint Type:</b> {found_type}<br><br>
            
            <b>Axis Direction:</b><br>
            [{axis.x:.6f}, {axis.y:.6f}, {axis.z:.6f}]<br><br>
            
            <b>Origin Position:</b><br>
            [{origin.x:.6f}, {origin.y:.6f}, {origin.z:.6f}] mm<br><br>
            
            <b>Connected Bodies:</b><br>
            • {self._get_joint_body(found_joint, 1)}<br>
            • {self._get_joint_body(found_joint, 2)}<br><br>
            
            <b>Is this axis correct?</b>
            """
        )

        self.highlightAxisButton.setText("Confirm Axis")
        self.RecheckButton.setText("Recheck axis")
        self.updateBackButtonState()
    # ============================================================
    # JOINT EXTRACTION HELPERS
    # ============================================================

    def _extract_revolute_axis(self, obj):
        """Extract axis and origin from a Revolute joint"""
        
        # Try to get from Reference2 (common for revolute)
        try:
            if hasattr(obj, "Reference2"):
                ref = obj.Reference2
                if isinstance(ref, (list, tuple)) and len(ref) > 0:
                    body = ref[0]
                    if isinstance(body, (list, tuple)):
                        body = body[0]
                    
                    # Try to get face from reference
                    if len(ref) > 1 and isinstance(ref[1], (list, tuple)):
                        face_name = ref[1][0]
                        if hasattr(body, "Shape"):
                            face = body.Shape.getElement(face_name)
                            origin = face.CenterOfMass
                            # Axis is along the face normal (cylindrical face)
                            # For revolute, we need the axis of the cylindrical face
                            if hasattr(face, "Surface") and hasattr(face.Surface, "Axis"):
                                axis = face.Surface.Axis
                            else:
                                # Fallback: use placement Z-axis
                                if hasattr(obj, "Placement"):
                                    axis = obj.Placement.Rotation.multVec(App.Vector(0, 0, 1))
                                else:
                                    axis = App.Vector(0, 0, 1)
                            return axis, origin
        except Exception as e:
            App.Console.PrintMessage(f"Revolute extraction (Reference2): {e}\n")
        
        # Fallback: use placement
        if hasattr(obj, "Placement"):
            origin = obj.Placement.Base
            axis = obj.Placement.Rotation.multVec(App.Vector(0, 0, 1))
            return axis, origin
        elif hasattr(obj, "Placement2"):
            origin = obj.Placement2.Base
            axis = obj.Placement2.Rotation.multVec(App.Vector(0, 0, 1))
            return axis, origin
        
        return App.Vector(0, 0, 1), App.Vector(0, 0, 0)

    def _extract_slider_axis(self, obj):
        """Extract axis and origin from a Slider joint"""
        
        # Slider joints: axis is the translation direction
        try:
            if hasattr(obj, "Placement"):
                origin = obj.Placement.Base
                axis = obj.Placement.Rotation.multVec(App.Vector(0, 0, 1))
                return axis, origin
            elif hasattr(obj, "Placement1"):
                origin = obj.Placement1.Base
                axis = obj.Placement1.Rotation.multVec(App.Vector(0, 0, 1))
                return axis, origin
        except:
            pass
        
        # Try to get from reference
        try:
            if hasattr(obj, "Reference1"):
                ref = obj.Reference1
                if isinstance(ref, (list, tuple)) and len(ref) > 0:
                    body = ref[0]
                    if isinstance(body, (list, tuple)):
                        body = body[0]
                    if hasattr(body, "Shape"):
                        origin = body.Shape.CenterOfMass
                        # Axis from placement
                        if hasattr(body, "Placement"):
                            axis = body.Placement.Rotation.multVec(App.Vector(0, 0, 1))
                        else:
                            axis = App.Vector(0, 0, 1)
                        return axis, origin
        except:
            pass
        
        return App.Vector(0, 0, 1), App.Vector(0, 0, 0)

    def _extract_cylindrical_axis(self, obj):
        """Extract axis and origin from a Cylindrical joint"""
        
        # Cylindrical joints have both rotation and translation along the same axis
        # Use similar logic to revolute
        try:
            if hasattr(obj, "Placement"):
                origin = obj.Placement.Base
                axis = obj.Placement.Rotation.multVec(App.Vector(0, 0, 1))
                return axis, origin
            elif hasattr(obj, "Placement2"):
                origin = obj.Placement2.Base
                axis = obj.Placement2.Rotation.multVec(App.Vector(0, 0, 1))
                return axis, origin
        except:
            pass
        
        # Try to get from reference
        try:
            if hasattr(obj, "Reference1"):
                ref = obj.Reference1
                if isinstance(ref, (list, tuple)) and len(ref) > 0:
                    body = ref[0]
                    if isinstance(body, (list, tuple)):
                        body = body[0]
                    if hasattr(body, "Shape"):
                        origin = body.Shape.CenterOfMass
                        if hasattr(body, "Placement"):
                            axis = body.Placement.Rotation.multVec(App.Vector(0, 0, 1))
                        else:
                            axis = App.Vector(0, 0, 1)
                        return axis, origin
        except:
            pass
        
        return App.Vector(0, 0, 1), App.Vector(0, 0, 0)

    def _extract_fixed_axis(self, obj):
        """Extract axis and origin from a Fixed joint"""
        
        # Fixed joints don't have an axis, but we can show the connection point
        # Use the placement or reference position
        
        try:
            if hasattr(obj, "Placement"):
                origin = obj.Placement.Base
                axis = App.Vector(0, 0, 1)  # No specific direction for fixed
                return axis, origin
        except:
            pass
        
        try:
            if hasattr(obj, "Reference1"):
                ref = obj.Reference1
                if isinstance(ref, (list, tuple)) and len(ref) > 0:
                    body = ref[0]
                    if isinstance(body, (list, tuple)):
                        body = body[0]
                    if hasattr(body, "Shape"):
                        origin = body.Shape.CenterOfMass
                        return App.Vector(0, 0, 1), origin
        except:
            pass
        
        return App.Vector(0, 0, 1), App.Vector(0, 0, 0)

    def _get_joint_body(self, obj, index):
        """Get the name of a body connected to a joint"""
        try:
            ref_prop = f"Reference{index}"
            if hasattr(obj, ref_prop):
                ref = getattr(obj, ref_prop)
                if isinstance(ref, (list, tuple)) and len(ref) > 0:
                    body = ref[0]
                    if isinstance(body, (list, tuple)):
                        body = body[0]
                    if hasattr(body, "Label"):
                        return body.Label
                    return str(body)
        except:
            pass
        return f"Body {index}"

    def highlightCentreOfMass(self, point):

        import pivy.coin as coin

        App.Console.PrintMessage(
            f"Centre of Mass = {point}\n"
        )

        # ------------------------------------------
        # Remove previous COM highlight
        # ------------------------------------------

        try:
            if hasattr(self, "comGraphic"):
                self.view.getSceneGraph().removeChild(
                    self.comGraphic
                )
        except Exception:
            pass

        # ------------------------------------------
        # Root scene graph
        # ------------------------------------------

        root = self.view.getSceneGraph()

        # ------------------------------------------
        # Annotation keeps the COM marker visible
        # above the model
        # ------------------------------------------

        annotation = coin.SoAnnotation()

        # ------------------------------------------
        # Position marker at global COM
        # ------------------------------------------

        transform = coin.SoTransform()

        transform.translation.setValue(
            point.x,
            point.y,
            point.z
        )

        # ------------------------------------------
        # Red COM sphere
        # ------------------------------------------

        material = coin.SoMaterial()

        material.diffuseColor = (
            1.0,
            0.0,
            0.0
        )

        material.emissiveColor = (
            1.0,
            0.0,
            0.0
        )

        # ------------------------------------------
        # Make it clearly visible
        # ------------------------------------------

        sphere = coin.SoSphere()

        sphere.radius = 8.0

        # ------------------------------------------
        # Build graphic
        # ------------------------------------------

        annotation.addChild(transform)
        annotation.addChild(material)
        annotation.addChild(sphere)

        # ------------------------------------------
        # Add to FreeCAD scene
        # ------------------------------------------

        root.addChild(annotation)

        self.comGraphic = annotation

    def showInitialBodyState(self):
        self.currentStep = 2

        App.Console.PrintMessage("\n=== Initial Body State ===\n")

        # --------------------------------------------------
        # Get the moving body
        # --------------------------------------------------

        body = self.movingBody

        App.Console.PrintMessage(
            f"Moving Body = {body.Name}\n"
        )

        # --------------------------------------------------
        # Calculate GLOBAL centre of mass
        # --------------------------------------------------

        # --------------------------------------------------
        # Calculate centre of mass
        # --------------------------------------------------

        shape = body.Shape

        globalCOM = None

        try:
            # Try the actual Body shape first
            globalCOM = shape.CenterOfMass

            App.Console.PrintMessage(
                f"Body Shape COM = {globalCOM}\n"
            )

        except Exception:

            # Body.Shape may be a Compound.
            # Calculate the COM from all solids.
            if hasattr(shape, "Solids") and len(shape.Solids) > 0:

                totalVolume = 0.0
                weightedCOM = App.Vector(0, 0, 0)

                for solid in shape.Solids:

                    volume = solid.Volume
                    com = solid.CenterOfMass

                    weightedCOM += com * volume
                    totalVolume += volume

                if totalVolume > 0:

                    globalCOM = weightedCOM / totalVolume

                    App.Console.PrintMessage(
                        f"Calculated Body COM = {globalCOM}\n"
                    )

        if globalCOM is None:

            App.Console.PrintError(
                "Unable to determine centre of mass.\n"
            )

            return
        # FreeCAD uses mm
        # DAP3D uses metres

        r = [
            globalCOM.x / 1000.0,
            globalCOM.y / 1000.0,
            globalCOM.z / 1000.0
        ]

        # --------------------------------------------------
        # Get initial orientation
        # --------------------------------------------------

        q = body.Placement.Rotation.Q

        # FreeCAD:
        # Q = (x, y, z, w)
        #
        # DAP3D:
        # p = (e0, e1, e2, e3)
        # where scalar comes first

        p = [
            q[3],
            q[0],
            q[1],
            q[2]
        ]

        App.Console.PrintMessage(
            f"COM = {globalCOM}\n"
        )

        App.Console.PrintMessage(
            f"R = {r}\n"
        )

        App.Console.PrintMessage(
            f"P = {p}\n"
        )

        # --------------------------------------------------
        # Highlight centre of mass
        # --------------------------------------------------

        self.highlightCentreOfMass(globalCOM)

        # --------------------------------------------------
        # Update Assistant
        # --------------------------------------------------

        self.assistantStatus.setText(
            "<b>Step 3 of 6</b><br><br>"
            "<b>Initial Body State</b><br><br>"
            f"I identified <b>{body.Label}</b> as the moving body.<br><br>"
            "The first DAP3D input is the body's initial "
            "position and orientation.<br><br>"
            "<b>Centre of Mass</b><br>"
            f"R = [{r[0]:.6f}, {r[1]:.6f}, {r[2]:.6f}] m<br><br>"
            "<b>Euler Parameters</b><br>"
            f"P = [{p[0]:.6f}, {p[1]:.6f}, "
            f"{p[2]:.6f}, {p[3]:.6f}]<br><br>"
            "The highlighted point represents the body's "
            "centre of mass.<br><br>"
            "<b>Is this correct?</b>"
        )

        self.assistantButtonYes.show()
        self.assistantButtonNo.show()

        # Remove previous connections
        try:
            self.assistantButtonYes.clicked.disconnect()
        except Exception:
            pass

        try:
            self.assistantButtonNo.clicked.disconnect()
        except Exception:
            pass

        # Connect buttons
        self.assistantButtonYes.clicked.connect(
            self.confirmInitialBodyState
        )

        self.assistantButtonNo.clicked.connect(
            self.recalculateInitialBodyState
        )


    def confirmInitialBodyState(self):

        App.Console.PrintMessage(
            "Initial body state confirmed.\n"
        )

        self.assistantButtonYes.hide()
        self.assistantButtonNo.hide()

        # ------------------------------------------
        # Move to mass properties
        # ------------------------------------------

        self.showMassProperties()


    def showMassProperties(self):
        self.currentStep = 3

        App.Console.PrintMessage(
            "\n=== Mass Properties ===\n"
        )

        # ------------------------------------------
        # Get moving body
        # ------------------------------------------

        body = self.movingBody

        if body is None:
            App.Console.PrintError(
                "No moving body detected.\n"
            )
            return

        App.Console.PrintMessage(
            f"Moving Body = {body.Name}\n"
        )

        shape = body.Shape

        # ------------------------------------------
        # Volume
        # ------------------------------------------

        volume_mm3 = shape.Volume

        App.Console.PrintMessage(
            f"Volume = {volume_mm3} mm^3\n"
        )

        # ------------------------------------------
        # Material density
        # ------------------------------------------

        density = None

        try:

            material = body.ShapeMaterial

            properties = material.Properties

            density_string = properties.get(
                "Density",
                None
            )

            if density_string is not None:

                if isinstance(density_string, str):
                    density = float(density_string.split()[0])
                else:
                    density = float(density_string)

        except Exception as e:

            App.Console.PrintError(
                f"Density extraction failed: {e}\n"
            )

        App.Console.PrintMessage(
            f"Density = {density} kg/mm^3\n"
        )

        # ------------------------------------------
        # Mass
        # ------------------------------------------

        if density is not None:

            mass = volume_mm3 * density

        else:

            mass = None

        App.Console.PrintMessage(
            f"Mass = {mass} kg\n"
        )

        # ------------------------------------------
        # Get solid
        # ------------------------------------------

        inertia = None

        if len(shape.Solids) > 0:

            solid = shape.Solids[0]

            try:

                inertia = solid.MatrixOfInertia

            except Exception as e:

                App.Console.PrintError(
                    f"Inertia extraction failed: {e}\n"
                )

        # ------------------------------------------
        # Convert inertia to kg m²
        # ------------------------------------------

        if inertia is not None and density is not None:

            conversion = density * 1e-6

            Ixx = inertia.A11 * conversion
            Ixy = inertia.A12 * conversion
            Ixz = inertia.A13 * conversion

            Iyx = inertia.A21 * conversion
            Iyy = inertia.A22 * conversion
            Iyz = inertia.A23 * conversion

            Izx = inertia.A31 * conversion
            Izy = inertia.A32 * conversion
            Izz = inertia.A33 * conversion

        else:

            Ixx = Ixy = Ixz = 0.0
            Iyx = Iyy = Iyz = 0.0
            Izx = Izy = Izz = 0.0

        # ------------------------------------------
        # Debug
        # ------------------------------------------

        App.Console.PrintMessage(
            f"Jxx = {Ixx} kg m^2\n"
        )

        App.Console.PrintMessage(
            f"Jxy = {Ixy} kg m^2\n"
        )

        App.Console.PrintMessage(
            f"Jxz = {Ixz} kg m^2\n"
        )

        App.Console.PrintMessage(
            f"Jyy = {Iyy} kg m^2\n"
        )

        App.Console.PrintMessage(
            f"Jyz = {Iyz} kg m^2\n"
        )

        App.Console.PrintMessage(
            f"Jzz = {Izz} kg m^2\n"
        )

        # ------------------------------------------
        # Display in Assistant
        # ------------------------------------------

        self.assistantStep(
            4,
            6,
            "Mass Properties",
            f"""
            I have analysed the moving body's mass properties.<br><br>

            <b>Moving Body</b><br>
            {body.Label}<br><br>

            <b>Mass</b><br>
            {mass:.9e} kg<br><br>

            <b>Mass Moment of Inertia Matrix</b><br><br>

            ⎡ {Ixx:.6e} &nbsp;&nbsp; {Ixy:.6e} &nbsp;&nbsp; {Ixz:.6e} ⎤<br>
            ⎢ {Iyx:.6e} &nbsp;&nbsp; {Iyy:.6e} &nbsp;&nbsp; {Iyz:.6e} ⎥<br>
            ⎣ {Izx:.6e} &nbsp;&nbsp; {Izy:.6e} &nbsp;&nbsp; {Izz:.6e} ⎦<br><br>

            <b>Units:</b> kg·m²<br><br>

            These properties will be used to define the
            body's mass and inertia properties in DAP3D.<br><br>

            <b>Are these mass properties correct?</b>
            """
        )

        # ------------------------------------------
        # Buttons
        # ------------------------------------------

        self.assistantButtonYes.show()
        self.assistantButtonNo.show()

        try:
            self.assistantButtonYes.clicked.disconnect()
        except Exception:
            pass

        try:
            self.assistantButtonNo.clicked.disconnect()
        except Exception:
            pass

        self.assistantButtonYes.clicked.connect(
            self.confirmMassProperties
        )

        self.assistantButtonNo.clicked.connect(
            self.recalculateMassProperties
        )

    def confirmMassProperties(self):
        self.currentStep = 4

        App.Console.PrintMessage(
            "Mass properties confirmed.\n"
        )

        self.assistantButtonYes.hide()
        self.assistantButtonNo.hide()
      
        self.assistantStatus.setText(
            "<b>Step 4 of 6</b><br><br>"
            "<b>Mass Properties Confirmed ✓</b><br><br>"
            "The body's mass and inertia properties "
            "have been accepted."
        )

    def showJointProperties(self):
        """Step 5: Display and confirm joint propertieS"""
        self.currentStep = 5	
        
        App.Console.PrintMessage("\n=== Joint Properties ===\n")
        
        # --------------------------------------------------
        # Find all joints in the assembly
        # --------------------------------------------------
        
        joints = []
        for obj in self.doc.Objects:
            # Try different property names for joint type
            joint_type = None
            for prop_name in ["JointType", "Type", "JointTypeId"]:
                if hasattr(obj, prop_name):
                    joint_type = getattr(obj, prop_name)
                    break
            
            # Also check if object name contains joint keywords
            if not joint_type:
                if "Joint" in obj.Name or "Joint" in obj.Label:
                    # Check if it has references (likely a joint)
                    if hasattr(obj, "Reference1") or hasattr(obj, "Reference2"):
                        joint_type = "Unknown"
            
            # Check if this is a joint
            is_joint = False
            if joint_type is not None:
                is_joint = True
            elif hasattr(obj, "Reference1") and hasattr(obj, "Reference2"):
                is_joint = True
            
            if is_joint:
                joints.append(obj)
                App.Console.PrintMessage(f"Found joint: {obj.Name} ({obj.Label})")
        
        # --------------------------------------------------
        # Store joints for later use
        # --------------------------------------------------
        
        self.detectedJoints = joints
        
        # --------------------------------------------------
        # Check if we found any joints
        # --------------------------------------------------
        
        if len(joints) == 0:
            self.assistantStep(
                5,
                6,
                "⚠️ No Joint Detected",
                """
                <b>⚠️ No Joints Found</b><br><br>
                
                I could not detect any joints in your assembly.<br><br>
                
                Please ensure:<br>
                • You have created at least one joint<br>
                • The joint is connected to the moving body<br>
                • The joint is properly defined<br><br>
                
                <b>Options:</b><br>
                • Click <b>"Recheck"</b> to scan again<br>
                • Click <b>"Skip"</b> to proceed with manual input
                """
            )
            
            # Add skip button if not already present
            if not hasattr(self, 'skipButton'):
                self.skipButton = QtWidgets.QPushButton("⏭ Skip (Manual Input)")
                self.skipButton.clicked.connect(self.skipJointStep)
                self.assistantLayout.addWidget(self.skipButton)
            
            self.skipButton.show()
            
            # Also show recheck
            self.RecheckButton.setText("Recheck joints")
            self.RecheckButton.clicked.disconnect()
            self.RecheckButton.clicked.connect(self.recheckJoints)
            self.RecheckButton.show()
            
            return
        
        # --------------------------------------------------
        # Get properties of the first joint
        # --------------------------------------------------
        
        joint = joints[0]
        
        # Extract joint type
        joint_type = "Unknown"
        for prop_name in ["JointType", "Type", "JointTypeId"]:
            if hasattr(joint, prop_name):
                joint_type = str(getattr(joint, prop_name))
                break
        
        # Extract axis direction
        axis = App.Vector(0, 0, 1)  # Default Z-axis
        position = App.Vector(0, 0, 0)
        
        if hasattr(joint, "Placement"):
            position = joint.Placement.Base
            axis = joint.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        elif hasattr(joint, "Placement2"):
            position = joint.Placement2.Base
            axis = joint.Placement2.Rotation.multVec(App.Vector(0, 0, 1))
        
        # Extract connected bodies
        body1 = "Unknown"
        body2 = "Unknown"
        
        if hasattr(joint, "Reference1"):
            ref1 = joint.Reference1
            if isinstance(ref1, (list, tuple)) and len(ref1) > 0:
                if isinstance(ref1[0], (list, tuple)):
                    body1 = ref1[0][0].Label if hasattr(ref1[0][0], "Label") else str(ref1[0][0])
                else:
                    body1 = ref1[0].Label if hasattr(ref1[0], "Label") else str(ref1[0])
        
        if hasattr(joint, "Reference2"):
            ref2 = joint.Reference2
            if isinstance(ref2, (list, tuple)) and len(ref2) > 0:
                if isinstance(ref2[0], (list, tuple)):
                    body2 = ref2[0][0].Label if hasattr(ref2[0][0], "Label") else str(ref2[0][0])
                else:
                    body2 = ref2[0].Label if hasattr(ref2[0], "Label") else str(ref2[0])
        
        # Determine which body is the moving body
        moving_body_name = self.movingBody.Label if self.movingBody else "Unknown"
        
        # Display in Assistant
        self.assistantStep(
            5,
            6,
            "Joint Properties",
            f"""
            I have detected the driving joint.<br><br>
            
            <b>Joint Name:</b> {joint.Label}<br>
            <b>Joint Type:</b> {joint_type}<br><br>
            
            <b>Axis of Rotation:</b><br>
            • Direction: [{axis.x:.6f}, {axis.y:.6f}, {axis.z:.6f}]<br>
            • Position: [{position.x:.6f}, {position.y:.6f}, {position.z:.6f}] mm<br><br>
            
            <b>Connected Bodies:</b><br>
            • Body 1: {body1}<br>
            • Body 2: {body2}<br><br>
            
            <b>Moving Body:</b><br>
            • {moving_body_name}<br><br>
            
            <b>Is this information correct?</b>
            """
        )
        
        # --------------------------------------------------
        # Store joint parameters for later use
        # --------------------------------------------------
        
        self.jointParams = {
            'joint': joint,
            'joint_type': joint_type,
            'axis': axis,
            'position': position,
            'body1': body1,
            'body2': body2,
            'moving_body': moving_body_name
        }
        
        # --------------------------------------------------
        # Show buttons
        # --------------------------------------------------
        
        self.assistantButtonYes.show()
        self.assistantButtonNo.show()
        
        # Remove previous connections
        try:
            self.assistantButtonYes.clicked.disconnect()
        except Exception:
            pass
        
        try:
            self.assistantButtonNo.clicked.disconnect()
        except Exception:
            pass
        
        # Connect buttons
        self.assistantButtonYes.clicked.connect(self.confirmJointProperties)
        self.assistantButtonNo.clicked.connect(self.recalculateJointProperties)
        
        # Hide skip button if visible
        if hasattr(self, 'skipButton'):
            self.skipButton.hide()
    def recheckJoints(self):
        """Recheck joints when none were found"""
        
        App.Console.PrintMessage("Rechecking joints...\n")
        
        self.assistantStatus.setText(
            "<b>Step 5 of 6</b><br><br>"
            "⏳ Rechecking for joints..."
        )
        
        QtWidgets.QApplication.processEvents()
        
        # Call showJointProperties again
        self.showJointProperties()

    def skipJointStep(self):
        """Skip joint detection and proceed with manual input"""
        
        App.Console.PrintMessage("Skipping joint detection...\n")
        
        if hasattr(self, 'skipButton'):
            self.skipButton.hide()
        
        # Ask user for manual joint input
        dialog = JointManualInputDialog(self.assembly)
        if dialog.exec_():
            # Store manual joint parameters
            self.jointParams = {
                'joint': None,
                'joint_type': 'Manual Input',
                'axis': dialog.axis,
                'position': dialog.position,
                'body1': dialog.body1,
                'body2': dialog.body2,
                'moving_body': dialog.moving_body
            }
            
            self.confirmJointProperties()

    def confirmJointProperties(self):
        """Step 5 confirmed – proceed to Step 6"""
        
        App.Console.PrintMessage("Joint properties confirmed.\n")
        
        self.assistantButtonYes.hide()
        self.assistantButtonNo.hide()
        
        # Hide any skip button
        if hasattr(self, 'skipButton'):
            self.skipButton.hide()
        
        # Move to Step 6
        self.finalizeAssistant()

    def recalculateJointProperties(self):
        """Recalculate joint properties"""
        
        App.Console.PrintMessage("Recalculating joint properties...\n")
        
        self.assistantButtonYes.hide()
        self.assistantButtonNo.hide()
        
        self.assistantStatus.setText(
            "<b>Step 5 of 6</b><br><br>"
            "⏳ Recalculating joint properties..."
        )
        
        QtWidgets.QApplication.processEvents()
        
        # Re-run joint detection
        self.showJointProperties()

    def finalizeAssistant(self):
        """Step 6: Finalize and prepare for simulation"""
        
        App.Console.PrintMessage("\n=== Finalizing Assistant ===\n")
        
        # --------------------------------------------------
        # Generate DAP3D input file content
        # --------------------------------------------------
        
        inBodies_content = self.generateInBodies()
        inJoints_content = self.generateInJoints()
        inPoints_content = self.generateInPoints()
        inVectors_content = self.generateInVectors()
        inForces_content = self.generateInForces()
        
        # --------------------------------------------------
        # Display summary to user
        # --------------------------------------------------
        
        mass_str = f"{self.bodyMass:.6e}" if hasattr(self, 'bodyMass') and self.bodyMass else "Unknown"
        
        self.assistantStep(
            6,
            6,
            "✅ Simulation Ready!",
            f"""
            <b>✅ Assembly setup complete!</b><br><br>
            
            All parameters have been confirmed:<br>
            • ✅ Body detected<br>
            • ✅ Center of Mass confirmed<br>
            • ✅ Mass and Inertia confirmed<br>
            • ✅ Joint axis confirmed<br><br>
            
            <b>Summary:</b><br>
            • Moving Body: {self.movingBody.Label if self.movingBody else 'Unknown'}<br>
            • Mass: {mass_str} kg<br>
            • Joint Type: {self.jointParams.get('joint_type', 'Unknown')}<br><br>
            
            <b>DAP3D Input Files Generated:</b><br>
            • ✓ inBodies.m<br>
            • ✓ inJoints.m<br>
            • ✓ inPoints.m<br>
            • ✓ inVectors.m<br>
            • ✓ inForces.m<br><br>
            
            Press <b>"Run Kinematics"</b> to run the simulation.
            """
        )
        
        # --------------------------------------------------
        # Store generated content for later use
        # --------------------------------------------------
        
        self.dap3dInputs = {
            'inBodies': inBodies_content,
            'inJoints': inJoints_content,
            'inPoints': inPoints_content,
            'inVectors': inVectors_content,
            'inForces': inForces_content
        }
        
        # --------------------------------------------------
        # Enable Run button
        # --------------------------------------------------
        
        self.form.RunKinematicsButton.setEnabled(True)
        self.form.RunKinematicsButton.setToolTip("Run kinematics simulation")

   
    def recalculateMassProperties(self):

        App.Console.PrintMessage(
            "Recalculating mass properties...\n"
        )

        self.assistantButtonYes.hide()
        self.assistantButtonNo.hide()

        self.assistantStatus.setText(
            "<b>Step 4 of 6</b><br><br>"
            "⏳ Recalculating mass properties..."
        )

        QtWidgets.QApplication.processEvents()

        self.showMassProperties()

    def recalculateInitialBodyState(self):

        App.Console.PrintMessage(
            "Recalculating initial body state...\n"
        )

        self.assistantButtonYes.hide()
        self.assistantButtonNo.hide()

        self.assistantStatus.setText(
            "<b>Step 3 of 6</b><br><br>"
            "⏳ Recalculating the initial body state..."
        )

        QtWidgets.QApplication.processEvents()

        self.showInitialBodyState()

    def setUiInitialValues(self):
        self.form.TimeStartSpinBox.setProperty("rawValue", self.simFeaturePy.aTimeStart.Value)
        self.form.TimeEndSpinBox.setProperty("rawValue", self.simFeaturePy.bTimeEnd.Value)
        self.form.TimeStepOutputSpinBox.setProperty(
            "rawValue", self.simFeaturePy.cTimeStepOutput.Value
        )
        self.form.GlobalErrorToleranceSpinBox.setProperty(
            "rawValue", self.simFeaturePy.fGlobalErrorTolerance
        )
        self.setFrameValue(0)
        self.form.FramesPerSecondSpinBox.setValue(self.simFeaturePy.jFramesPerSecond)

    def setSpinboxPrecision(self, spinbox, precision, unit=App.Units.TimeSpan):
        q = App.Units.Quantity()
        q.Unit = unit
        q.Format = {"Precision": precision}
        spinbox.setProperty("value", q)

    def accept(self):
        self.deactivate()
        UtilsAssembly.restoreAssemblyPartsPlacements(self.assembly, self.initialPlcs)
        App.closeActiveTransaction()
        return True

    def reject(self):
        self.deactivate()
        App.closeActiveTransaction(True)
        return True

    def deactivate(self):
        self.animationTimer.stop()
        self.simFeaturePy.Proxy.setMotionsChangedCallback(None)
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()

    def onTimeStartChanged(self, quantity):
        self.simFeaturePy.aTimeStart = self.form.TimeStartSpinBox.property("rawValue")

    def onTimeEndChanged(self, quantity):
        self.simFeaturePy.bTimeEnd = self.form.TimeEndSpinBox.property("rawValue")

    def onTimeStepOutputChanged(self, quantity):
        self.simFeaturePy.cTimeStepOutput = self.form.TimeStepOutputSpinBox.property("rawValue")

    def onGlobalErrorToleranceChanged(self, quantity):
        self.simFeaturePy.fGlobalErrorTolerance = self.form.GlobalErrorToleranceSpinBox.property(
            "rawValue"
        )

    def onItemDoubleClicked(self, item):
        row = self.form.motionList.row(item)
        if row < len(self.simFeaturePy.Group):
            motion = self.simFeaturePy.Group[row]
            motion.ViewObject.Proxy.openEditDialog()
            self.onMotionsChanged()

    def createSimulationObject(self):
        sim_group = UtilsAssembly.getSimulationGroup(self.assembly)
        self.simFeaturePy = sim_group.newObject("App::FeaturePython", "Simulation")
        Simulation(self.simFeaturePy)
        ViewProviderSimulation(self.simFeaturePy.ViewObject)

    def createMotionObject(self, motionType, joint, formula):
        motion = self.assembly.newObject("App::FeaturePython", "Motion")
        Motion(motion, motionType, joint, formula)
        ViewProviderMotion(motion.ViewObject)

        listOfMotions = self.simFeaturePy.Group
        listOfMotions.append(motion)
        self.simFeaturePy.Group = listOfMotions

    def onMotionsChanged(self):
        self.form.motionList.clear()
        for motion in self.simFeaturePy.Group:
            self.form.motionList.addItem(motion.Label)

    def runKinematics(self):
        self.assembly.generateSimulation(self.simFeaturePy)
        nFrms = self.assembly.numberOfFrames()
        self.form.frameSlider.setMaximum(nFrms - 1)
        self.setFrameValue(nFrms - 1)
        self.form.groupBox_player.show()

    def onFrameChanged(self, val):
        self.assembly.updateForFrame(val)
        self.form.FrameLabel.setText(translate("Assembly", "Frame" + " " + str(val)))
        time = float(val * self.simFeaturePy.cTimeStepOutput)
        self.form.FrameTimeLabel.setText(f"{time:.2f} s")

    def onFramesPerSecondChanged(self):
        self.simFeaturePy.jFramesPerSecond = self.form.FramesPerSecondSpinBox.value()

    def playBackward(self):
        pass

    def animationTimerStartForward(self):
        self.direction = 1
        self.animationTimerStart()

    def animationTimerStartBackward(self):
        self.direction = -1
        self.animationTimerStart()

    def animationTimerStart(self):
        self.animationTimer.stop()
        self.currentFrm = self.form.frameSlider.value()
        self.startFrm = 1
        self.endFrm = self.form.frameSlider.maximum()
        if self.startFrm >= self.endFrm:
            return

        self.fps = self.simFeaturePy.jFramesPerSecond
        self.deltaTime = 1.0 / self.fps
        self.startTime = time.time()
        self.index = self.currentFrm
        self.animationTimer.setInterval(self.deltaTime * 1000)  # ms
        self.animationTimer.start()

    def playAnimation(self):
        range_ = self.endFrm - self.startFrm
        offset = self.currentFrm - self.startFrm
        count = int((time.time() - self.startTime) / self.deltaTime)
        self.index = ((self.direction * count + offset) % range_) + self.startFrm
        self.setFrameValue(self.index)


    def displayLastFrame(self):
        nFrms = self.assembly.numberOfFrames()
        self.setFrameValue(nFrms - 1)

    def stepBackward(self):
        self.animationTimer.stop()

        nextFrm = self.form.frameSlider.value() - 1
        if nextFrm < 1:
            nextFrm = self.form.frameSlider.maximum()  # wraparound
        self.setFrameValue(nextFrm)

    def stepForward(self):
        self.animationTimer.stop()

        nextFrm = self.form.frameSlider.value() + 1
        if nextFrm > self.form.frameSlider.maximum():
            nextFrm = 1  # wraparound
        self.setFrameValue(nextFrm)

    def setFrameValue(self, val):
        if val < 1:
            val = 1
        if val > self.form.frameSlider.maximum():
            val = self.form.frameSlider.maximum()

        self.form.frameSlider.setValue(val)

    def stopAnimation(self):
        self.animationTimer.stop()

    def goBackStep(self):
        """Go back to the previous step"""
        
        if not hasattr(self, 'currentStep') or self.currentStep <= 0:
            App.Console.PrintMessage("Already at first step.\n")
            return
        
        self.currentStep -= 1
        
        App.Console.PrintMessage(f"Going back to Step {self.currentStep}\n")
        
        # Re-display the previous step
        if self.currentStep == 0:
            self.analyseAssembly()
        elif self.currentStep == 1:
            self.highlightDrivingAxis()
        elif self.currentStep == 2:
            self.showInitialBodyState()
        elif self.currentStep == 3:
            self.showMassProperties()
        elif self.currentStep == 4:
            self.assistantStatus.setText(
                "<b>Step 4 of 6</b><br><br>"
                "<b>Mass Properties Confirmed ✓</b><br><br>"
                "The body's mass and inertia properties "
                "have been accepted."
            )
        elif self.currentStep == 5:
            self.showJointProperties()
        
        self.updateBackButtonState()

    def updateBackButtonState(self):
        """Enable or disable the back button based on current step"""
        if not hasattr(self, 'currentStep'):
            self.currentStep = 0
        self.backButton.setEnabled(self.currentStep > 0)

    def addMotionClicked(self):
        dialog = MotionEditDialog(self.assembly)
        if dialog.exec_():
            self.createMotionObject(dialog.motionType, dialog.joint, dialog.formula)

    # Taskbox keyboard event handler
    def eventFilter(self, watched, event):
        if self.form is not None and watched == self.form.motionList:
            if event.type() == QtCore.QEvent.ShortcutOverride:
                if event.key() == QtCore.Qt.Key_Delete:
                    event.accept()
                    return True  # Indicate that the event has been handled
                return False

            elif event.type() == QtCore.QEvent.KeyPress:
                if event.key() == QtCore.Qt.Key_Delete:
                    self.deleteSelectedMotions()
                    return True  # Consume the event

        return super().eventFilter(watched, event)

    def deleteSelectedMotions(self):
        selected_indexes = self.form.motionList.selectedIndexes()
        sorted_indexes = sorted(selected_indexes, key=lambda x: x.row(), reverse=True)
        for index in sorted_indexes:
            row = index.row()
            if row < len(self.simFeaturePy.Group):
                motion = self.simFeaturePy.Group[row]
                # First remove the link from the viewObj
                self.simFeaturePy.Group.remove(motion)
                # Delete the object
                motion.Document.removeObject(motion.Name)


if App.GuiUp:
    Gui.addCommand("Assembly_CreateSimulation", CommandCreateSimulation())