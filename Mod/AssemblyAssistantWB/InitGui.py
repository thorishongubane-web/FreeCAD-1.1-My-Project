import FreeCADGui as Gui

class AssemblyAssistantWorkbench(Gui.Workbench):

    MenuText = "Assembly Assistant"
    ToolTip = "Assembly Assistant Workbench"
    Icon = ""

    def Initialize(self):

        from Commands import SmartRevolute

        Gui.addCommand(
            "AssemblyAssistant_SmartRevolute",
            SmartRevolute.SmartRevoluteCommand()
        )

        self.appendToolbar(
            "Assembly Assistant",
            ["AssemblyAssistant_SmartRevolute"]
        )

        self.appendMenu(
            "Assembly Assistant",
            ["AssemblyAssistant_SmartRevolute"]
        )

    def GetClassName(self):
        return "Gui::PythonWorkbench"

Gui.addWorkbench(AssemblyAssistantWorkbench())