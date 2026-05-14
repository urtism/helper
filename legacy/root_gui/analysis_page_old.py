# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '/home/jarvis/git/Powercall/PowercallGUI/pygui/analysis_page.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
#from os.path import expanduser
import os.path
import subprocess

class MyMessageBox(QMessageBox):
    def __init__(self):
        QMessageBox.__init__(self)
        self.setSizeGripEnabled(True)

    def event(self, e):
        result = QMessageBox.event(self, e)

        self.setMinimumHeight(150)
        self.setMaximumHeight(16777215)
        self.setMinimumWidth(900)
        self.setMaximumWidth(16777215)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        textEdit = self.findChild(QTextEdit)
        if textEdit != None :
            textEdit.setMinimumHeight(150)
            textEdit.setMaximumHeight(16777215)
            textEdit.setMinimumWidth(900)
            textEdit.setMaximumWidth(16777215)
            textEdit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return result

class Browse(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.show()

    def initUI(self):
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)     
        self.show()


class Analysis_page(QtWidgets.QWidget):
    def __init__(self, parent = None):
        super(Analysis_page, self).__init__(parent)
        self.setupUi()
        
    def setupUi(self):
        
        self.setObjectName("Analysis_page")
        self.resize(1177, 890)

        self.verticalLayout_2 = QtWidgets.QVBoxLayout(self)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.frame = QtWidgets.QFrame()
        self.frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame.setObjectName("frame")
        self.gridLayout_2 = QtWidgets.QGridLayout(self.frame)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.splitter_2 = QtWidgets.QSplitter(self.frame)
        self.splitter_2.setOrientation(QtCore.Qt.Horizontal)
        self.splitter_2.setObjectName("splitter_2")
        self.splitter = QtWidgets.QSplitter(self.splitter_2)
        self.splitter.setOrientation(QtCore.Qt.Vertical)
        self.splitter.setObjectName("splitter")
        self.groupBox = QtWidgets.QGroupBox(self.splitter)
        self.groupBox.setAlignment(QtCore.Qt.AlignCenter)
        self.groupBox.setObjectName("groupBox")
        self.formLayout = QtWidgets.QFormLayout(self.groupBox)
        self.formLayout.setObjectName("formLayout")
        self.label = QtWidgets.QLabel(self.groupBox)
        self.label.setObjectName("label")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.label)
        self.runID_lineEdit = QtWidgets.QLineEdit(self.groupBox)
        self.runID_lineEdit.setObjectName("runID_lineEdit")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.runID_lineEdit)
        self.label_2 = QtWidgets.QLabel(self.groupBox)
        self.label_2.setObjectName("label_2")
        self.formLayout.setWidget(2, QtWidgets.QFormLayout.LabelRole, self.label_2)
        self.panels_comboBox = QtWidgets.QComboBox(self.groupBox)
        self.panels_comboBox.setObjectName("panels_comboBox")
        self.panels_comboBox.addItem("")
        self.panels_comboBox.addItem("")
        self.panels_comboBox.addItem("")
        self.panels_comboBox.addItem("")
        self.panels_comboBox.addItem("")
        self.panels_comboBox.addItem("")
        self.panels_comboBox.addItem("")
        self.formLayout.setWidget(2, QtWidgets.QFormLayout.FieldRole, self.panels_comboBox)
        self.label_3 = QtWidgets.QLabel(self.groupBox)
        self.label_3.setObjectName("label_3")
        self.formLayout.setWidget(4, QtWidgets.QFormLayout.LabelRole, self.label_3)
        self.pipeline_comboBox = QtWidgets.QComboBox(self.groupBox)
        self.pipeline_comboBox.setObjectName("pipeline_comboBox")
        self.pipeline_comboBox.addItem("")
        self.pipeline_comboBox.addItem("")
        self.pipeline_comboBox.addItem("")
        self.formLayout.setWidget(4, QtWidgets.QFormLayout.FieldRole, self.pipeline_comboBox)
        self.groupBox_3 = QtWidgets.QGroupBox(self.splitter)
        self.groupBox_3.setAlignment(QtCore.Qt.AlignCenter)
        self.groupBox_3.setObjectName("groupBox_3")
        self.gridLayout = QtWidgets.QGridLayout(self.groupBox_3)
        self.gridLayout.setObjectName("gridLayout")


        self.samplesheet_label = QtWidgets.QLabel(self.groupBox_3)
        self.samplesheet_label.setObjectName("samplesheet_label")
        self.gridLayout.addWidget(self.samplesheet_label, 0, 0, 1, 1)
        self.samplesheet_toolButton = QtWidgets.QToolButton(self.groupBox_3)
        self.samplesheet_toolButton.setObjectName("samplesheet_toolButton")
        self.gridLayout.addWidget(self.samplesheet_toolButton, 0, 2, 1, 1)
        self.samplesheet_lineEdit = QtWidgets.QLineEdit(self.groupBox_3)
        self.samplesheet_lineEdit.setObjectName("samplesheet_lineEdit")
        self.gridLayout.addWidget(self.samplesheet_lineEdit, 0, 1, 1, 1)

        self.workdir_label = QtWidgets.QLabel(self.groupBox_3)
        self.workdir_label.setObjectName("workdir_label")
        self.gridLayout.addWidget(self.workdir_label, 1, 0, 1, 1)
        self.workdir_toolButton = QtWidgets.QToolButton(self.groupBox_3)
        self.workdir_toolButton.setObjectName("workdir_toolButton")
        self.gridLayout.addWidget(self.workdir_toolButton, 1, 2, 1, 1)
        self.workDir_lineEdit = QtWidgets.QLineEdit(self.groupBox_3)
        self.workDir_lineEdit.setObjectName("workDir_lineEdit")
        self.workDir_lineEdit.setStyleSheet("color: grey;")
        self.workDir_lineEdit.setText(os.path.expanduser("~"))
        self.gridLayout.addWidget(self.workDir_lineEdit, 1, 1, 1, 1)

        self.tools_label = QtWidgets.QLabel(self.groupBox_3)
        self.tools_label.setObjectName("tools_label")
        self.gridLayout.addWidget(self.tools_label, 2, 0, 1, 1)
        self.tools_toolButton = QtWidgets.QToolButton(self.groupBox_3)
        self.tools_toolButton.setObjectName("tools_toolButton")
        self.gridLayout.addWidget(self.tools_toolButton, 2, 2, 1, 1)
        self.tools_lineEdit = QtWidgets.QLineEdit(self.groupBox_3)
        self.tools_lineEdit.setObjectName("tools_lineEdit")
        self.gridLayout.addWidget(self.tools_lineEdit, 2, 1, 1, 1)


        self.groupBox_2 = QtWidgets.QGroupBox(self.splitter_2)
        self.groupBox_2.setAlignment(QtCore.Qt.AlignCenter)
        self.groupBox_2.setFlat(False)
        self.groupBox_2.setCheckable(False)
        self.groupBox_2.setObjectName("groupBox_2")
        self.formLayout_2 = QtWidgets.QFormLayout(self.groupBox_2)
        self.formLayout_2.setObjectName("formLayout_2")
        self.alignment_check = QtWidgets.QCheckBox(self.groupBox_2)
        self.alignment_check.setChecked(True)
        self.alignment_check.setObjectName("alignment_check")
        self.formLayout_2.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.alignment_check)
        self.read_group_check = QtWidgets.QCheckBox(self.groupBox_2)
        self.read_group_check.setChecked(True)
        self.read_group_check.setObjectName("read_group_check")
        self.formLayout_2.setWidget(4, QtWidgets.QFormLayout.LabelRole, self.read_group_check)
        self.markDup_check = QtWidgets.QCheckBox(self.groupBox_2)
        self.markDup_check.setChecked(True)
        self.markDup_check.setObjectName("markDup_check")
        self.formLayout_2.setWidget(5, QtWidgets.QFormLayout.LabelRole, self.markDup_check)
        self.indel_real_check = QtWidgets.QCheckBox(self.groupBox_2)
        self.indel_real_check.setChecked(True)
        self.indel_real_check.setObjectName("indel_real_check")
        self.formLayout_2.setWidget(6, QtWidgets.QFormLayout.LabelRole, self.indel_real_check)
        self.BQSR_check = QtWidgets.QCheckBox(self.groupBox_2)
        self.BQSR_check.setChecked(True)
        self.BQSR_check.setObjectName("BQSR_check")
        self.formLayout_2.setWidget(7, QtWidgets.QFormLayout.LabelRole, self.BQSR_check)
        spacerItem = QtWidgets.QSpacerItem(20, 60, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.formLayout_2.setItem(8, QtWidgets.QFormLayout.LabelRole, spacerItem)
        self.variant_call_check = QtWidgets.QCheckBox(self.groupBox_2)
        self.variant_call_check.setChecked(True)
        self.variant_call_check.setObjectName("variant_call_check")
        self.formLayout_2.setWidget(10, QtWidgets.QFormLayout.LabelRole, self.variant_call_check)
        self.variant_filter_check = QtWidgets.QCheckBox(self.groupBox_2)
        self.variant_filter_check.setChecked(True)
        self.variant_filter_check.setObjectName("variant_filter_check")
        self.formLayout_2.setWidget(11, QtWidgets.QFormLayout.LabelRole, self.variant_filter_check)
        self.variant_ann_check = QtWidgets.QCheckBox(self.groupBox_2)
        self.variant_ann_check.setChecked(True)
        self.variant_ann_check.setObjectName("variant_ann_check")
        self.formLayout_2.setWidget(12, QtWidgets.QFormLayout.LabelRole, self.variant_ann_check)
        self.CNV_check = QtWidgets.QCheckBox(self.groupBox_2)
        self.CNV_check.setChecked(True)
        self.CNV_check.setObjectName("CNV_check")
        self.formLayout_2.setWidget(15, QtWidgets.QFormLayout.LabelRole, self.CNV_check)
        spacerItem1 = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.formLayout_2.setItem(2, QtWidgets.QFormLayout.LabelRole, spacerItem1)
        self.label_6 = QtWidgets.QLabel(self.groupBox_2)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.label_6.setFont(font)
        self.label_6.setObjectName("label_6")
        self.formLayout_2.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.label_6)
        self.label_7 = QtWidgets.QLabel(self.groupBox_2)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.label_7.setFont(font)
        self.label_7.setObjectName("label_7")
        self.formLayout_2.setWidget(3, QtWidgets.QFormLayout.LabelRole, self.label_7)
        self.label_8 = QtWidgets.QLabel(self.groupBox_2)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.label_8.setFont(font)
        self.label_8.setObjectName("label_8")
        self.formLayout_2.setWidget(9, QtWidgets.QFormLayout.LabelRole, self.label_8)
        self.label_9 = QtWidgets.QLabel(self.groupBox_2)
        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)
        self.label_9.setFont(font)
        self.label_9.setObjectName("label_9")
        self.formLayout_2.setWidget(14, QtWidgets.QFormLayout.LabelRole, self.label_9)
        spacerItem2 = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.formLayout_2.setItem(13, QtWidgets.QFormLayout.LabelRole, spacerItem2)
        self.gridLayout_2.addWidget(self.splitter_2, 0, 0, 1, 1)
        self.verticalLayout_2.addWidget(self.frame)
        self.frame_2 = QtWidgets.QFrame()
        self.frame_2.setMaximumSize(QtCore.QSize(16777215, 101))
        self.frame_2.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame_2.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame_2.setObjectName("frame_2")
        self.verticalLayout = QtWidgets.QVBoxLayout(self.frame_2)
        self.verticalLayout.setObjectName("verticalLayout")
        self.start_analysis_pushButton = QtWidgets.QPushButton(self.frame_2)
        self.start_analysis_pushButton.setMinimumSize(QtCore.QSize(0, 51))
        self.start_analysis_pushButton.setMaximumSize(QtCore.QSize(16777215, 71))
        self.start_analysis_pushButton.setObjectName("start_analysis_pushButton")
        self.verticalLayout.addWidget(self.start_analysis_pushButton)
        self.verticalLayout_2.addWidget(self.frame_2)

        self.retranslateUi()
        QtCore.QMetaObject.connectSlotsByName(self)
        self.show()
        self.init_functions()

    def getsamplesheet(self):
        ss_options = QFileDialog.Options()
        ss_options |= QFileDialog.DontUseNativeDialog
        ss, _ = QFileDialog.getOpenFileName(self,"Choose Samplesheet", os.path.expanduser("~"),"Sample sheet files (*.samplesheet *.ss)", options=ss_options)
        if ss:
            self.samplesheet_lineEdit.setText(ss)
            if self.runID_lineEdit.text() =='':
                self.runID_lineEdit.setText(ss.split('/')[-1].split('.')[0])

    def getToolscfg(self):
        tool_options = QFileDialog.Options()
        tool_options |= QFileDialog.DontUseNativeDialog
        starting_folder = os.path.dirname(os.path.realpath(__file__))+'/configs'
        file, _ = QFileDialog.getOpenFileName(self,"Choose Tools configuration file", starting_folder,"Tools configuration files (*.cfg *.cfg.json)", options=tool_options)
        if file:
            self.tools_lineEdit.setText(file)

    def getworkdir(self):
        wdir_options = QFileDialog.Options()
        wdir_options |= QFileDialog.DontUseNativeDialog
        wdir_options |= QFileDialog.ShowDirsOnly
        wdir_options |= QFileDialog.DontResolveSymlinks
        folder = QFileDialog.getExistingDirectory(self,"Choose Working dir", os.path.expanduser("~") + '/Scrivania', options=wdir_options)
        if folder:
            self.workDir_lineEdit.setStyleSheet("color: black;")
            self.workDir_lineEdit.setText(folder)

    def get_workflow(self):
        workflow = ''

        if self.alignment_check.isChecked(): workflow += 'A'

        if self.read_group_check.isChecked(): workflow += 'R'
        if self.markDup_check.isChecked(): workflow += 'M'
        if self.indel_real_check.isChecked(): workflow += 'I'
        if self.BQSR_check.isChecked(): workflow += 'B'

        if self.variant_call_check.isChecked(): workflow += 'V'
        if self.variant_filter_check.isChecked(): workflow += 'F'
        if self.variant_ann_check.isChecked(): workflow += 'E'

        if self.CNV_check.isChecked(): workflow += 'C'

        return workflow

    def start_analysis(self):
        runid = self.runID_lineEdit.text()
        panel = self.panels_comboBox.currentText()
        pipeline = self.pipeline_comboBox.currentText()
        samplesheet = self.samplesheet_lineEdit.text()
        workdir = '/'.join([self.workDir_lineEdit.text(),runid])
        toolscfg = self.tools_lineEdit.text()
        workflow = self.get_workflow()


        if runid == '':
            miss_runID = QMessageBox()  
            miss_runID.setWindowTitle('Error!')
            miss_runID.setText('Invalid runID!')
            miss_runID.setIcon(QMessageBox.Critical)
            miss_runID.exec()

        elif not ((samplesheet.endswith('.ss') or  samplesheet.endswith('.samplesheet')) and os.path.exists(samplesheet)):
            miss_Samplesheet = QMessageBox()
            miss_Samplesheet.setWindowTitle('Error!')
            miss_Samplesheet.setText('Invalid samplesheet!')
            miss_Samplesheet.setIcon(QMessageBox.Critical)
            miss_Samplesheet.exec()
        else:
            start = MyMessageBox()
            start.setWindowTitle('Last Check')
            start.setIcon(QMessageBox.Information)
            start.setText('\n\n'.join(['RunID: \t\t' + runid,
                'Panel: \t\t' + panel, 
                'Pipeline: \t\t' + pipeline,
                'Samplesheet: \t' + samplesheet,
                'Tools cfg: \t\t' + toolscfg,
                'WorkDir: \t\t' + workdir]))
            start.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
            returnValue = start.exec()
            if returnValue == QMessageBox.Ok:
                powercall_main = os.path.dirname(os.path.realpath(__file__))+'/bin/main.py'
                args = ['python3', powercall_main]
                args += ['--run_id', runid]
                args += ['--panel', panel.split(' ')[-1]]
                args += ['--analysis', pipeline]
                args += ['--workdir', workdir]
                args += ['--workflow', workflow]
                args += ['--samplesheet', samplesheet]
                args += ['--cfg', toolscfg]
                print(' '.join(args))
                self.hide()
                success = subprocess.call(args)
                if not success:
                    success = QMessageBox()
                    success.setWindowTitle('Success!')
                    success.setText('The analysis has been successfully completed')
                    success.setIcon(QMessageBox.Information)
                    success.exec()


    def init_functions(self):
        self.start_analysis_pushButton.clicked.connect(self.start_analysis)
        self.samplesheet_toolButton.clicked.connect(self.getsamplesheet)
        self.workdir_toolButton.clicked.connect(self.getworkdir)
        self.tools_toolButton.clicked.connect(self.getToolscfg)

    def retranslateUi(self):
        _translate = QtCore.QCoreApplication.translate
        self.setWindowTitle(_translate("Analysis_page", "Analysis Settings"))
        self.groupBox.setTitle(_translate("Analysis_page", "Analysis Informations"))
        self.label.setText(_translate("Analysis_page", "Run ID"))
        self.label_2.setText(_translate("Analysis_page", "Panel Name"))
        self.panels_comboBox.setItemText(0, _translate("Analysis_page", "Illumina TrusightCardio"))
        self.panels_comboBox.setItemText(1, _translate("Analysis_page", "Illumina TrusightCancer"))
        self.panels_comboBox.setItemText(2, _translate("Analysis_page", "Illumina TrusightOne"))
        self.panels_comboBox.setItemText(3, _translate("Analysis_page", "SophiaGen HCS"))
        self.panels_comboBox.setItemText(4, _translate("Analysis_page", "Agilent CardioV1"))
        self.panels_comboBox.setItemText(5, _translate("Analysis_page", "Agilent AneurysmV1"))
        self.panels_comboBox.setItemText(6, _translate("Analysis_page", "Agilent CancerV1"))
        self.label_3.setText(_translate("Analysis_page", "Pipeline"))
        self.pipeline_comboBox.setItemText(0, _translate("Analysis_page", "Germline"))
        self.pipeline_comboBox.setItemText(1, _translate("Analysis_page", "Somatic"))
        self.pipeline_comboBox.setItemText(2, _translate("Analysis_page", "Cellfree"))
        self.groupBox_3.setTitle(_translate("Analysis_page", "Files and Folders"))  
        self.samplesheet_label.setText(_translate("Analysis_page", "Samplesheet"))
        self.samplesheet_toolButton.setText(_translate("Analysis_page", "..."))
        self.workdir_toolButton.setText(_translate("Analysis_page", "..."))
        self.workdir_label.setText(_translate("Analysis_page", "Working directory"))     
        self.tools_label.setText(_translate("Analysis_page", "Tools config file"))
        self.tools_toolButton.setText(_translate("Analysis_page", "..."))
        self.groupBox_2.setTitle(_translate("Analysis_page", "Workflow"))
        self.alignment_check.setText(_translate("Analysis_page", "FASTQ Alignment"))
        self.read_group_check.setText(_translate("Analysis_page", "Add or Replace Read Groups"))
        self.markDup_check.setText(_translate("Analysis_page", "Marking Duplicates"))
        self.indel_real_check.setText(_translate("Analysis_page", "Indel Realignement"))
        self.BQSR_check.setText(_translate("Analysis_page", "Base Quality Score Recalibration"))
        self.variant_call_check.setText(_translate("Analysis_page", "Variant Calling"))
        self.variant_filter_check.setText(_translate("Analysis_page", "Variant Filtering"))
        self.variant_ann_check.setText(_translate("Analysis_page", "Variant Annotation"))
        self.CNV_check.setText(_translate("Analysis_page", "CNV Calling"))
        self.label_6.setText(_translate("Analysis_page", "READS ALIGNMENT"))
        self.label_7.setText(_translate("Analysis_page", "DATA PREPROCESSING"))
        self.label_8.setText(_translate("Analysis_page", "VARIANT CALLING AND POST PROCESSING"))
        self.label_9.setText(_translate("Analysis_page", "COPY NUMBER ANALYSIS"))
        self.start_analysis_pushButton.setText(_translate("Analysis_page", "Start POWERCALL V2.0"))

