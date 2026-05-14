from PyQt5 import QtCore, QtGui, QtWidgets
from HelperGUI import sheet_compiler as sc
from HelperGUI import samplesheet_designer as ssd
from HelperGUI import analysis_page as ap
from HelperGUI import experiment_builder as eb
from HelperGUI import tool_settings as ts
from HelperGUI import pipeline_designer as pd


class Ui_MainWindow(object):

    def __init__(self):
        self.setupUi

    def open_samplesheet_compiler(self):
        #print('open_samplesheet_compiler')
        #self.samplesheet_editor = sc.Samplesheet_editor()
        #self.samplesheet_editor.show()

        #print('open_samplesheet_designer')
        self.samplesheet_designer = ssd.samplesheet_designer()
        self.samplesheet_designer.show()


    def open_pipeline_editor(self):
        #print('open_pipeline_editor')
        self.pipeline_designer = pd.Pipeline_designer()
        self.pipeline_designer.show()

    def open_tools_settings(self):
        #print('open_tools_settings')
        self.tool_settings = ts.tool_settings()
        self.tool_settings.show()

    def open_panel_editor(self):
        #print('open_panel_editor')
        self.experiment_builder = eb.Experiment_builder()
        self.experiment_builder.show()

    def open_analysis_page(self):
        #print('open_analysis_page')
        self.analysis_page = ap.Analysis_page()
        self.analysis_page.show()

    def setupUi(self, MainWindow):
        MainWindow.setObjectName("Helper")
        MainWindow.resize(1185, 937)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(MainWindow.sizePolicy().hasHeightForWidth())
        MainWindow.setSizePolicy(sizePolicy)
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.centralwidget.sizePolicy().hasHeightForWidth())
        self.centralwidget.setSizePolicy(sizePolicy)
        self.centralwidget.setObjectName("centralwidget")
        self.gridLayout = QtWidgets.QGridLayout(self.centralwidget)
        self.gridLayout.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
        self.gridLayout.setObjectName("gridLayout")
        self.frame_2 = QtWidgets.QFrame(self.centralwidget)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.MinimumExpanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame_2.sizePolicy().hasHeightForWidth())
        self.frame_2.setSizePolicy(sizePolicy)
        self.frame_2.setMaximumSize(QtCore.QSize(1161, 151))
        self.frame_2.setLayoutDirection(QtCore.Qt.LeftToRight)
        self.frame_2.setAutoFillBackground(False)
        self.frame_2.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame_2.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame_2.setObjectName("frame_2")
        self.gridLayout_3 = QtWidgets.QGridLayout(self.frame_2)
        self.gridLayout_3.setObjectName("gridLayout_3")
        self.label = QtWidgets.QLabel(self.frame_2)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label.sizePolicy().hasHeightForWidth())
        self.label.setSizePolicy(sizePolicy)
        self.label.setTextFormat(QtCore.Qt.AutoText)
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setObjectName("label")
        self.gridLayout_3.addWidget(self.label, 0, 0, 1, 1, QtCore.Qt.AlignHCenter|QtCore.Qt.AlignVCenter)
        self.gridLayout.addWidget(self.frame_2, 0, 0, 1, 1)
        self.frame = QtWidgets.QFrame(self.centralwidget)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame.sizePolicy().hasHeightForWidth())
        self.frame.setSizePolicy(sizePolicy)
        self.frame.setMaximumSize(QtCore.QSize(1161, 631))
        self.frame.setObjectName("frame")
        self.compileSS_Button = QtWidgets.QPushButton(self.frame)
        self.compileSS_Button.setGeometry(QtCore.QRect(90, 90, 401, 131))
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.compileSS_Button.sizePolicy().hasHeightForWidth())
        self.compileSS_Button.setSizePolicy(sizePolicy)
        self.compileSS_Button.setMaximumSize(QtCore.QSize(441, 131))
        self.compileSS_Button.setObjectName("compileSS_Button")
        self.pipelineEdit_Button = QtWidgets.QPushButton(self.frame)
        self.pipelineEdit_Button.setGeometry(QtCore.QRect(660, 90, 401, 131))
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.pipelineEdit_Button.sizePolicy().hasHeightForWidth())
        self.pipelineEdit_Button.setSizePolicy(sizePolicy)
        self.pipelineEdit_Button.setMaximumSize(QtCore.QSize(441, 131))
        self.pipelineEdit_Button.setObjectName("pipelineEdit_Button")
        self.toolsSet_Button = QtWidgets.QPushButton(self.frame)
        self.toolsSet_Button.setGeometry(QtCore.QRect(660, 260, 401, 131))
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.toolsSet_Button.sizePolicy().hasHeightForWidth())
        self.toolsSet_Button.setSizePolicy(sizePolicy)
        self.toolsSet_Button.setMaximumSize(QtCore.QSize(441, 131))
        self.toolsSet_Button.setObjectName("toolsSet_Button")
        self.panelInfo_Button = QtWidgets.QPushButton(self.frame)
        self.panelInfo_Button.setGeometry(QtCore.QRect(90, 260, 401, 131))
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.panelInfo_Button.sizePolicy().hasHeightForWidth())
        self.panelInfo_Button.setSizePolicy(sizePolicy)
        self.panelInfo_Button.setMaximumSize(QtCore.QSize(441, 131))
        self.panelInfo_Button.setObjectName("panelInfo_Button")
        self.start_Analysis_Button = QtWidgets.QPushButton(self.frame)
        self.start_Analysis_Button.setGeometry(QtCore.QRect(10, 490, 1141, 71))
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.start_Analysis_Button.sizePolicy().hasHeightForWidth())
        self.start_Analysis_Button.setSizePolicy(sizePolicy)
        self.start_Analysis_Button.setObjectName("start_Analysis_Button")
        self.gridLayout.addWidget(self.frame, 1, 0, 1, 1)
        MainWindow.setCentralWidget(self.centralwidget)

        self.retranslateUi(MainWindow)
        
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

        self.setup_buttons()

    def setup_buttons(self):
        self.compileSS_Button.clicked.connect(self.open_samplesheet_compiler)
        self.pipelineEdit_Button.clicked.connect(self.open_pipeline_editor)
        self.toolsSet_Button.clicked.connect(self.open_tools_settings)
        self.panelInfo_Button.clicked.connect(self.open_panel_editor)
        self.start_Analysis_Button.clicked.connect(self.open_analysis_page)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("Helper", "Helper"))
        self.label.setText(_translate("Helper", "Helper v1.0"))
        self.compileSS_Button.setText(_translate("Helper", "COMPILE SAMPLE SHEET "))
        self.pipelineEdit_Button.setText(_translate("Helper", "ADD or EDIT PIPELINE"))
        self.toolsSet_Button.setText(_translate("Helper", "TOOLS SETTINGS"))
        self.panelInfo_Button.setText(_translate("Helper", "ADD or EDIT GENE PANEL INFO"))
        self.start_Analysis_Button.setText(_translate("Helper", "START ANALYSIS"))


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()
    ui = Ui_MainWindow()
    ui.setupUi(MainWindow)
    MainWindow.show()
    sys.exit(app.exec_())
