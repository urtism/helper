# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '/home/jarvis/git/Powercall2/Powercall/form.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!



from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import os.path
import subprocess
import json


class Browse(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.show()

    def initUI(self):
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)     
        self.show()

class Experiment_builder(QtWidgets.QWidget):
    
    def __init__(self, parent = None):
        super(Experiment_builder, self).__init__(parent)
        self.setupUi()


    def setupUi(self):
        #Experiment_builder.setObjectName("Experiment_builder")
        #Experiment_builder.resize(947, 827)
        self.verticalLayout = QtWidgets.QVBoxLayout(self)
        self.verticalLayout.setObjectName("verticalLayout")
        self.frame = QtWidgets.QFrame(self)
        self.frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame.setObjectName("frame")
        self.gridLayout = QtWidgets.QGridLayout(self.frame)
        self.gridLayout.setObjectName("gridLayout")
        self.targetBed_lineEdit = QtWidgets.QLineEdit(self.frame)
        self.targetBed_lineEdit.setObjectName("targetBed_lineEdit")
        self.gridLayout.addWidget(self.targetBed_lineEdit, 6, 1, 1, 1)
        self.GeneList_toolButton = QtWidgets.QToolButton(self.frame)

        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.GeneList_toolButton.sizePolicy().hasHeightForWidth())
        self.GeneList_toolButton.setSizePolicy(sizePolicy)
        self.GeneList_toolButton.setObjectName("GeneList_toolButton")
        self.gridLayout.addWidget(self.GeneList_toolButton, 3, 2, 1, 1)
        self.Delete_Experiment_pushbutton = QtWidgets.QPushButton(self.frame)
        palette = QtGui.QPalette()
        brush = QtGui.QBrush(QtGui.QColor(0, 0, 0))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.WindowText, brush)
        brush = QtGui.QBrush(QtGui.QColor(252, 125, 125, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.Button, brush)
        brush = QtGui.QBrush(QtGui.QColor(255, 250, 250, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.Light, brush)
        brush = QtGui.QBrush(QtGui.QColor(253, 187, 187, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.Midlight, brush)
        brush = QtGui.QBrush(QtGui.QColor(126, 62, 62, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.Dark, brush)
        brush = QtGui.QBrush(QtGui.QColor(168, 83, 83, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.Mid, brush)
        brush = QtGui.QBrush(QtGui.QColor(0, 0, 0))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.Text, brush)
        brush = QtGui.QBrush(QtGui.QColor(255, 255, 255))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.BrightText, brush)
        brush = QtGui.QBrush(QtGui.QColor(0, 0, 0))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.ButtonText, brush)
        brush = QtGui.QBrush(QtGui.QColor(255, 255, 255))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.Base, brush)
        brush = QtGui.QBrush(QtGui.QColor(252, 125, 125, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.Window, brush)
        brush = QtGui.QBrush(QtGui.QColor(0, 0, 0))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.Shadow, brush)
        brush = QtGui.QBrush(QtGui.QColor(253, 190, 190, 223))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.AlternateBase, brush)
        brush = QtGui.QBrush(QtGui.QColor(255, 255, 220))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.ToolTipBase, brush)
        brush = QtGui.QBrush(QtGui.QColor(0, 0, 0))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.ToolTipText, brush)
        brush = QtGui.QBrush(QtGui.QColor(0, 0, 0, 128))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.PlaceholderText, brush)
        brush = QtGui.QBrush(QtGui.QColor(0, 0, 0))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Inactive, QtGui.QPalette.WindowText, brush)
        brush = QtGui.QBrush(QtGui.QColor(252, 125, 125, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Inactive, QtGui.QPalette.Button, brush)
        brush = QtGui.QBrush(QtGui.QColor(255, 250, 250, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Inactive, QtGui.QPalette.Light, brush)
        brush = QtGui.QBrush(QtGui.QColor(253, 187, 187, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Inactive, QtGui.QPalette.Midlight, brush)
        brush = QtGui.QBrush(QtGui.QColor(126, 62, 62, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Inactive, QtGui.QPalette.Dark, brush)
        brush = QtGui.QBrush(QtGui.QColor(168, 83, 83, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Inactive, QtGui.QPalette.Mid, brush)
        brush = QtGui.QBrush(QtGui.QColor(0, 0, 0))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Inactive, QtGui.QPalette.Text, brush)
        brush = QtGui.QBrush(QtGui.QColor(255, 255, 255))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Inactive, QtGui.QPalette.BrightText, brush)
        brush = QtGui.QBrush(QtGui.QColor(0, 0, 0))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Inactive, QtGui.QPalette.ButtonText, brush)
        brush = QtGui.QBrush(QtGui.QColor(255, 255, 255))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Inactive, QtGui.QPalette.Base, brush)
        brush = QtGui.QBrush(QtGui.QColor(252, 125, 125, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Inactive, QtGui.QPalette.Window, brush)
        brush = QtGui.QBrush(QtGui.QColor(0, 0, 0))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Inactive, QtGui.QPalette.Shadow, brush)
        brush = QtGui.QBrush(QtGui.QColor(253, 190, 190, 223))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Inactive, QtGui.QPalette.AlternateBase, brush)
        brush = QtGui.QBrush(QtGui.QColor(255, 255, 220))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Inactive, QtGui.QPalette.ToolTipBase, brush)
        brush = QtGui.QBrush(QtGui.QColor(0, 0, 0))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Inactive, QtGui.QPalette.ToolTipText, brush)
        brush = QtGui.QBrush(QtGui.QColor(0, 0, 0, 128))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Inactive, QtGui.QPalette.PlaceholderText, brush)
        brush = QtGui.QBrush(QtGui.QColor(126, 62, 62, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Disabled, QtGui.QPalette.WindowText, brush)
        brush = QtGui.QBrush(QtGui.QColor(252, 125, 125, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Disabled, QtGui.QPalette.Button, brush)
        brush = QtGui.QBrush(QtGui.QColor(255, 250, 250, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Disabled, QtGui.QPalette.Light, brush)
        brush = QtGui.QBrush(QtGui.QColor(253, 187, 187, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Disabled, QtGui.QPalette.Midlight, brush)
        brush = QtGui.QBrush(QtGui.QColor(126, 62, 62, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Disabled, QtGui.QPalette.Dark, brush)
        brush = QtGui.QBrush(QtGui.QColor(168, 83, 83, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Disabled, QtGui.QPalette.Mid, brush)
        brush = QtGui.QBrush(QtGui.QColor(126, 62, 62, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Disabled, QtGui.QPalette.Text, brush)
        brush = QtGui.QBrush(QtGui.QColor(255, 255, 255))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Disabled, QtGui.QPalette.BrightText, brush)
        brush = QtGui.QBrush(QtGui.QColor(126, 62, 62, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText, brush)
        brush = QtGui.QBrush(QtGui.QColor(252, 125, 125, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Disabled, QtGui.QPalette.Base, brush)
        brush = QtGui.QBrush(QtGui.QColor(252, 125, 125, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Disabled, QtGui.QPalette.Window, brush)
        brush = QtGui.QBrush(QtGui.QColor(0, 0, 0))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Disabled, QtGui.QPalette.Shadow, brush)
        brush = QtGui.QBrush(QtGui.QColor(252, 125, 125, 191))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Disabled, QtGui.QPalette.AlternateBase, brush)
        brush = QtGui.QBrush(QtGui.QColor(255, 255, 220))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Disabled, QtGui.QPalette.ToolTipBase, brush)
        brush = QtGui.QBrush(QtGui.QColor(0, 0, 0))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Disabled, QtGui.QPalette.ToolTipText, brush)
        brush = QtGui.QBrush(QtGui.QColor(0, 0, 0, 128))
        brush.setStyle(QtCore.Qt.SolidPattern)
        palette.setBrush(QtGui.QPalette.Disabled, QtGui.QPalette.PlaceholderText, brush)
        self.Delete_Experiment_pushbutton.setPalette(palette)
        self.Delete_Experiment_pushbutton.setObjectName("Delete_Experiment_pushbutton")
        self.gridLayout.addWidget(self.Delete_Experiment_pushbutton, 1, 2, 1, 1)
        self.label_5 = QtWidgets.QLabel(self.frame)
        self.label_5.setObjectName("label_5")
        self.gridLayout.addWidget(self.label_5, 6, 0, 1, 1)
        self.targetList_toolButton = QtWidgets.QToolButton(self.frame)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.targetList_toolButton.sizePolicy().hasHeightForWidth())
        self.targetList_toolButton.setSizePolicy(sizePolicy)
        self.targetList_toolButton.setObjectName("targetList_toolButton")
        self.gridLayout.addWidget(self.targetList_toolButton, 5, 2, 1, 1)
        self.panelname_comboBox = QtWidgets.QComboBox(self.frame)
        self.panelname_comboBox.setEditable(True)
        self.panelname_comboBox.setObjectName("comboBox")
        self.gridLayout.addWidget(self.panelname_comboBox, 1, 1, 1, 1)
        self.label_7 = QtWidgets.QLabel(self.frame)
        self.label_7.setObjectName("label_7")
        self.gridLayout.addWidget(self.label_7, 8, 0, 1, 1)
        self.label_2 = QtWidgets.QLabel(self.frame)
        self.label_2.setObjectName("label_2")
        self.gridLayout.addWidget(self.label_2, 3, 0, 1, 1)
        self.transc_lineEdit = QtWidgets.QLineEdit(self.frame)
        self.transc_lineEdit.setObjectName("transc_lineEdit")
        self.gridLayout.addWidget(self.transc_lineEdit, 4, 1, 1, 1)
        self.CNVCallsModel_toolButton = QtWidgets.QToolButton(self.frame)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.CNVCallsModel_toolButton.sizePolicy().hasHeightForWidth())
        self.CNVCallsModel_toolButton.setSizePolicy(sizePolicy)
        self.CNVCallsModel_toolButton.setObjectName("CNVCallsModel_toolButton")
        self.gridLayout.addWidget(self.CNVCallsModel_toolButton, 10, 2, 1, 1)
        self.label_6 = QtWidgets.QLabel(self.frame)
        self.label_6.setObjectName("label_6")
        self.gridLayout.addWidget(self.label_6, 9, 0, 1, 1)
        self.frame_4 = QtWidgets.QFrame(self.frame)
        self.frame_4.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame_4.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame_4.setObjectName("frame_4")
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(self.frame_4)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.label_8 = QtWidgets.QLabel(self.frame_4)
        self.label_8.setEnabled(True)
        self.label_8.setFrameShadow(QtWidgets.QFrame.Plain)
        self.label_8.setAlignment(QtCore.Qt.AlignCenter)
        self.label_8.setObjectName("label_8")
        self.verticalLayout_2.addWidget(self.label_8)
        self.gridLayout.addWidget(self.frame_4, 7, 0, 1, 3)
        self.tech_comboBox = QtWidgets.QComboBox(self.frame)
        self.tech_comboBox.setObjectName("tech_comboBox")
        self.gridLayout.addWidget(self.tech_comboBox, 2, 1, 1, 1)
        self.targetBed_toolButton = QtWidgets.QToolButton(self.frame)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.targetBed_toolButton.sizePolicy().hasHeightForWidth())
        self.targetBed_toolButton.setSizePolicy(sizePolicy)
        self.targetBed_toolButton.setObjectName("targetBed_toolButton")
        self.gridLayout.addWidget(self.targetBed_toolButton, 6, 2, 1, 1)
        self.targetList_lineEdit = QtWidgets.QLineEdit(self.frame)
        self.targetList_lineEdit.setObjectName("targetList_lineEdit")
        self.gridLayout.addWidget(self.targetList_lineEdit, 5, 1, 1, 1)
        self.genelist_lineEdit = QtWidgets.QLineEdit(self.frame)
        self.genelist_lineEdit.setObjectName("genelist_lineEdit")
        self.gridLayout.addWidget(self.genelist_lineEdit, 3, 1, 1, 1)
        self.label_10 = QtWidgets.QLabel(self.frame)
        self.label_10.setObjectName("label_10")
        self.gridLayout.addWidget(self.label_10, 10, 0, 1, 1)
        self.transc_toolButton = QtWidgets.QToolButton(self.frame)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.transc_toolButton.sizePolicy().hasHeightForWidth())
        self.transc_toolButton.setSizePolicy(sizePolicy)
        self.transc_toolButton.setObjectName("transc_toolButton")
        self.gridLayout.addWidget(self.transc_toolButton, 4, 2, 1, 1)
        self.label = QtWidgets.QLabel(self.frame)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 1, 0, 1, 1)
        self.CNVtargetList_toolButton = QtWidgets.QToolButton(self.frame)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.CNVtargetList_toolButton.sizePolicy().hasHeightForWidth())
        self.CNVtargetList_toolButton.setSizePolicy(sizePolicy)
        self.CNVtargetList_toolButton.setObjectName("CNVtargetList_toolButton")
        self.gridLayout.addWidget(self.CNVtargetList_toolButton, 8, 2, 1, 1)
        spacerItem = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum)
        self.gridLayout.addItem(spacerItem, 11, 1, 1, 1)
        self.frame_3 = QtWidgets.QFrame(self.frame)
        self.frame_3.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame_3.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame_3.setObjectName("frame_3")
        self.verticalLayout_3 = QtWidgets.QVBoxLayout(self.frame_3)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.label_9 = QtWidgets.QLabel(self.frame_3)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Minimum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_9.sizePolicy().hasHeightForWidth())
        self.label_9.setSizePolicy(sizePolicy)
        font = QtGui.QFont()
        font.setFamily("FreeSans")
        font.setPointSize(16)
        self.label_9.setFont(font)
        self.label_9.setTextFormat(QtCore.Qt.AutoText)
        self.label_9.setScaledContents(False)
        self.label_9.setAlignment(QtCore.Qt.AlignCenter)
        self.label_9.setObjectName("label_9")
        self.verticalLayout_3.addWidget(self.label_9)
        self.gridLayout.addWidget(self.frame_3, 0, 0, 1, 3)
        self.label_4 = QtWidgets.QLabel(self.frame)
        self.label_4.setObjectName("label_4")
        self.gridLayout.addWidget(self.label_4, 5, 0, 1, 1)
        self.CNVTargetlist_lineEdit = QtWidgets.QLineEdit(self.frame)
        self.CNVTargetlist_lineEdit.setObjectName("CNVTargetlist_lineEdit")
        self.gridLayout.addWidget(self.CNVTargetlist_lineEdit, 8, 1, 1, 1)
        self.label_11 = QtWidgets.QLabel(self.frame)
        self.label_11.setObjectName("label_11")
        self.gridLayout.addWidget(self.label_11, 2, 0, 1, 1)
        self.CNVPloidyModel_lineEdit = QtWidgets.QLineEdit(self.frame)
        self.CNVPloidyModel_lineEdit.setObjectName("lineEdit")
        self.gridLayout.addWidget(self.CNVPloidyModel_lineEdit, 9, 1, 1, 1)
        self.CNVPloidyModel_toolButton = QtWidgets.QToolButton(self.frame)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.CNVPloidyModel_toolButton.sizePolicy().hasHeightForWidth())
        self.CNVPloidyModel_toolButton.setSizePolicy(sizePolicy)
        self.CNVPloidyModel_toolButton.setObjectName("CNVPloidyModel_toolButton")
        self.gridLayout.addWidget(self.CNVPloidyModel_toolButton, 9, 2, 1, 1)
        self.CNVCallsModel_lineEdit = QtWidgets.QLineEdit(self.frame)
        self.CNVCallsModel_lineEdit.setObjectName("CNVCallsModel_lineEdit")
        self.gridLayout.addWidget(self.CNVCallsModel_lineEdit, 10, 1, 1, 1)
        self.label_3 = QtWidgets.QLabel(self.frame)
        self.label_3.setObjectName("label_3")
        self.gridLayout.addWidget(self.label_3, 4, 0, 1, 1)
        self.verticalLayout.addWidget(self.frame)
        self.frame_2 = QtWidgets.QFrame(self)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame_2.sizePolicy().hasHeightForWidth())
        self.frame_2.setSizePolicy(sizePolicy)
        self.frame_2.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame_2.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame_2.setObjectName("frame_2")
        self.horizontalLayout = QtWidgets.QHBoxLayout(self.frame_2)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.CancelButton = QtWidgets.QPushButton(self.frame_2)
        self.CancelButton.setObjectName("CancelButton")
        self.horizontalLayout.addWidget(self.CancelButton)
        self.SaveButton = QtWidgets.QPushButton(self.frame_2)
        self.SaveButton.setObjectName("SaveButton")
        self.horizontalLayout.addWidget(self.SaveButton)
        self.verticalLayout.addWidget(self.frame_2)

        self.retranslateUi(self)
        self.init_functions()
        QtCore.QMetaObject.connectSlotsByName(self)

        self.experiment_config = self.get_config()
        self.panelname_comboBox.addItem("")
        self.panelname_comboBox.addItems(self.experiment_config["list"])
        self.tech_comboBox.addItems(["","Capture Enrichment","Amplicon"])

    def retranslateUi(self, Experiment_builder):
        _translate = QtCore.QCoreApplication.translate
        Experiment_builder.setWindowTitle(_translate("Experiment_builder", "Experiment Builder"))
        self.GeneList_toolButton.setText(_translate("Experiment_builder", "Search..."))
        self.Delete_Experiment_pushbutton.setText(_translate("Experiment_builder", "DELETE Panel"))
        self.label_5.setText(_translate("Experiment_builder", "Target File.bed:"))
        self.targetList_toolButton.setText(_translate("Experiment_builder", "Search..."))
        self.label_7.setText(_translate("Experiment_builder", "CNV Target File.list:"))
        self.label_2.setText(_translate("Experiment_builder", "Gene List:"))
        self.CNVCallsModel_toolButton.setText(_translate("Experiment_builder", "Search..."))
        self.label_6.setText(_translate("Experiment_builder", "CNV GATK Ploidy Model path:"))
        self.label_8.setText(_translate("Experiment_builder", "Useful information for the CNVs analysis with GATK"))
        self.targetBed_toolButton.setText(_translate("Experiment_builder", "Search..."))
        self.label_10.setText(_translate("Experiment_builder", "CNV GATK Calls Model path:"))
        self.transc_toolButton.setText(_translate("Experiment_builder", "Search..."))
        self.label.setText(_translate("Experiment_builder", "Panel Name:"))
        self.CNVtargetList_toolButton.setText(_translate("Experiment_builder", "Search..."))
        self.label_9.setText(_translate("Experiment_builder", "Add or Edit Experiment Information"))
        self.label_4.setText(_translate("Experiment_builder", "Target File.list:"))
        self.label_11.setText(_translate("Experiment_builder", "Panel Chemistry:"))
        self.CNVPloidyModel_toolButton.setText(_translate("Experiment_builder", "Search..."))
        self.label_3.setText(_translate("Experiment_builder", "Principal Transcript List:"))
        self.CancelButton.setText(_translate("Experiment_builder", "Reset Experiment"))
        self.SaveButton.setText(_translate("Experiment_builder", "Save Experiment"))

    def get_genelist(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        file, _ = QFileDialog.getOpenFileName(self,"Choose Gene List", os.path.expanduser("~"), options=options)
        if file:
            self.genelist_lineEdit.setText(file)

    def get_Transcriptlist(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        starting_folder = os.path.dirname(os.path.realpath(__file__))+'/configs'
        file, _ = QFileDialog.getOpenFileName(self,"Choose Transcript list file", starting_folder, options=options)
        if file:
            self.transc_lineEdit.setText(file)

    def get_Targetlist(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        file, _ = QFileDialog.getOpenFileName(self,"Choose Target.list file", os.path.expanduser("~"), options=options)
        if file:
            self.targetList_lineEdit.setText(file)

    def get_Targetbed(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        file, _ = QFileDialog.getOpenFileName(self,"Choose Target.bed file", os.path.expanduser("~"), options=options)
        if file:
            self.targetBed_lineEdit.setText(file)

    def get_CNVTargetlist(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        file, _ = QFileDialog.getOpenFileName(self,"Choose Target.list file for CNV Analysis", os.path.expanduser("~"), options=options)
        if file:
            self.CNVTargetlist_lineEdit.setText(file)

    def get_CNVPloidyModel(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        folder = QFileDialog.getExistingDirectory(self,"Choose GATK Ploidy Model Dir for CNV Analysis", os.path.expanduser("~"), options=options)
        if folder:
            self.CNVPloidyModel_lineEdit.setText(folder)


    def get_CNVCallsModel(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        options |= QFileDialog.ShowDirsOnly
        options |= QFileDialog.DontResolveSymlinks   
        folder = QFileDialog.getExistingDirectory(self,"Choose GATK Ploidy Model Dir for CNV Analysis", os.path.expanduser("~"), options=options)
        if folder:
            self.CNVCallsModel_lineEdit.setText(folder)

    def init_functions(self):
        self.GeneList_toolButton.clicked.connect(self.get_genelist)
        self.transc_toolButton.clicked.connect(self.get_Transcriptlist)
        self.targetList_toolButton.clicked.connect(self.get_Targetlist)
        self.targetBed_toolButton.clicked.connect(self.get_Targetbed)

        self.CNVtargetList_toolButton.clicked.connect(self.get_CNVTargetlist)
        self.CNVPloidyModel_toolButton.clicked.connect(self.get_CNVPloidyModel)
        self.CNVCallsModel_toolButton.clicked.connect(self.get_CNVCallsModel)

        self.CancelButton.clicked.connect(self.cancel_Experiment)
        self.SaveButton.clicked.connect(self.save_Experiment)
        self.Delete_Experiment_pushbutton.clicked.connect(self.delete_Experiment)

        self.panelname_comboBox.activated.connect(self.popolate_experiment)
    
    def cancel_Experiment(self):
        self.tech_comboBox.setCurrentIndex(0)     
        self.genelist_lineEdit.setText("")
        self.transc_lineEdit.setText("")
        self.targetList_lineEdit.setText("")
        self.targetBed_lineEdit.setText("")
        
        self.CNVCallsModel_lineEdit.setText("")
        self.CNVPloidyModel_lineEdit.setText("")
        self.CNVTargetlist_lineEdit.setText("")


    def save_Experiment(self):

        msgBox = QMessageBox()
        msgBox.setWindowTitle('Save Experiment')
        msgBox.setText('Do you want to save Experiment: ' + self.panelname_comboBox.currentText() +' ?')
        msgBox.setStandardButtons(QMessageBox.Save | QMessageBox.Cancel);
        msgBox.setIcon(QMessageBox.Question)
        ret = msgBox.exec()
        if ret == QMessageBox.Save:
            experiment_list = self.experiment_config["list"]
            experiment = self.panelname_comboBox.currentText()
            if experiment != "" and experiment != "select Experiment":
                if experiment not in experiment_list:
                    self.experiment_config["list"] += [experiment]
                    self.panelname_comboBox.addItem(experiment)

                self.experiment_config[experiment] = {
                    "panel_name":experiment,
                    "panel_technology": self.tech_comboBox.currentText(),
                    "gene_list":self.genelist_lineEdit.text(), 
                    "transcripts_list":self.transc_lineEdit.text(),
                    "target_list":self.targetList_lineEdit.text(),
                    "target_bed":self.targetBed_lineEdit.text(),
                    "cnv_calls_model":self.CNVCallsModel_lineEdit.text(),
                    "cnv_ploidy_model":self.CNVPloidyModel_lineEdit.text(),
                    "cnv_target_list":self.CNVTargetlist_lineEdit.text()}

                with open(os.path.dirname(os.path.realpath(__file__))+'/configs/experiment.cfg', 'w') as cfg:
                    json.dump(self.experiment_config, cfg, indent=4)


    def delete_Experiment(self):

        msgBox = QMessageBox()
        msgBox.setWindowTitle('Delete Experiment')
        msgBox.setText('Do you want to delete Experiment: ' + self.panelname_comboBox.currentText() +'?')
        msgBox.setStandardButtons(QMessageBox.Yes | QMessageBox.No);
        msgBox.setIcon(QMessageBox.Warning)
        ret = msgBox.exec()

        if ret == QMessageBox.Yes:
            experiment_list = self.experiment_config["list"]
            experiment = self.panelname_comboBox.currentText()
            if experiment in experiment_list:
                experiment_list.remove(experiment)
                del  self.experiment_config[experiment]
            with open(os.path.dirname(os.path.realpath(__file__))+'/configs/experiment.cfg', 'w') as cfg:
                    json.dump(self.experiment_config, cfg, indent=4)
            current = self.panelname_comboBox.currentIndex()
            self.panelname_comboBox.removeItem(current)
            self.panelname_comboBox.setCurrentIndex(0)
            self.cancel_Experiment()


    def get_config(self):
        starting_folder = os.path.dirname(os.path.realpath(__file__))+'/configs'
        return json.loads((open(starting_folder+'/experiment.cfg').read()).encode('utf8'))


    def popolate_experiment(self):
        experiment_list = self.experiment_config["list"]
        experiment = self.panelname_comboBox.currentText()
        if experiment != "" and experiment in experiment_list:
           
            self.tech_comboBox.setCurrentText(self.experiment_config[experiment]["panel_technology"])
            self.genelist_lineEdit.setText(self.experiment_config[experiment]["gene_list"])
            self.transc_lineEdit.setText(self.experiment_config[experiment]["transcripts_list"])
            self.targetList_lineEdit.setText(self.experiment_config[experiment]["target_list"])
            self.targetBed_lineEdit.setText(self.experiment_config[experiment]["target_bed"])            
            self.CNVCallsModel_lineEdit.setText(self.experiment_config[experiment]["cnv_calls_model"])
            self.CNVPloidyModel_lineEdit.setText(self.experiment_config[experiment]["cnv_ploidy_model"])
            self.CNVTargetlist_lineEdit.setText(self.experiment_config[experiment]["cnv_target_list"])