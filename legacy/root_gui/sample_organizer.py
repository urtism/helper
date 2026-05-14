# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '/home/jarvis/git/Powercall2/Powercall/sample_organizer.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!

from PyQt5 import QtCore, QtGui, QtWidgets
import sys
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5 import QtCore, QtGui, QtWidgets


class sample_organizer(QWidget):
    def __init__(self, parent = None):        
        super(sample_organizer, self).__init__(parent)
        self.setupUi()
        self.init_functions()

    def setupUi(self):
        self.sample_organization = {}

        self.setObjectName("sample_organizer")
        self.resize(400, 300)
        self.formLayout = QtWidgets.QFormLayout(self)
        self.formLayout.setObjectName("formLayout")
        self.Org_label = QtWidgets.QLabel(self)
        self.Org_label.setObjectName("Org_label")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.Org_label)
        self.Org_type_label = QtWidgets.QLabel(self)
        self.Org_type_label.setText("")
        self.Org_type_label.setObjectName("Org_type_label")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.Org_type_label)
        self.Cancel_org_pushButton = QtWidgets.QPushButton(self)
        self.Cancel_org_pushButton.setObjectName("Cancel_org_pushButton")
        self.formLayout.setWidget(3, QtWidgets.QFormLayout.LabelRole, self.Cancel_org_pushButton)
        self.Accept_pushButton = QtWidgets.QPushButton(self)
        self.Accept_pushButton.setObjectName("Accept_pushButton")
        self.formLayout.setWidget(3, QtWidgets.QFormLayout.FieldRole, self.Accept_pushButton)
        self.Org_tableWidget = QtWidgets.QTableWidget(self)
        self.Org_tableWidget.setObjectName("Org_tableWidget")
        self.Org_tableWidget.setColumnCount(0)
        self.Org_tableWidget.setRowCount(0)
        self.formLayout.setWidget(2, QtWidgets.QFormLayout.SpanningRole, self.Org_tableWidget)
        self.Addsample_pushButton = QtWidgets.QPushButton(self)
        self.Addsample_pushButton.setObjectName("Addsample_pushButton")
        self.formLayout.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.Addsample_pushButton)

        self.retranslateUi()
        QtCore.QMetaObject.connectSlotsByName(self)

    def retranslateUi(self):
        _translate = QtCore.QCoreApplication.translate
        self.setWindowTitle(_translate("Form", "Form"))
        self.Org_label.setText(_translate("Form", "Organization:"))
        self.Cancel_org_pushButton.setText(_translate("Form", "Cancel"))
        self.Accept_pushButton.setText(_translate("Form", "Accept"))
        self.Addsample_pushButton.setText(_translate("Form", "Add Sample"))


    def init_functions(self):
        self.Addsample_pushButton.clicked.connect(self.add_sample)
        self.Cancel_org_pushButton.clicked.connect(self.cancel_table)
        self.Accept_pushButton.clicked.connect(self.accept_table)
        self.Org_tableWidget.customContextMenuRequested.connect(self.show_Info_Menu)


    def init_table(self, org, sample_list):
        if org == 'only cases':
            labels = ('Sample ID', 'CASE')
            self.Org_tableWidget.setColumnCount(2)
            for sample in sample_list:
                self.add_sample()
        
        elif org == 'case-control':
            labels = ('Sample ID', 'CASE', 'CONTROL')
            self.Org_tableWidget.setColumnCount(3)

        elif org == 'trio':
            labels = ('Sample ID', 'CASE', 'PARENT 1', 'PARENT 2')
            self.Org_tableWidget.setColumnCount(4)
        

        self.Org_tableWidget.setHorizontalHeaderLabels(labels)
        self.Org_tableWidget.horizontalHeader().setStretchLastSection(True)
        self.Org_tableWidget.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)     
        self.Org_tableWidget.setContextMenuPolicy(Qt.CustomContextMenu) 



    def set_Sample_organizer(self,org, sample_list, samples):
        self.org = org
        self.sample_list = sample_list
        self.samples = samples
        self.Org_type_label.setText(org)
        self.init_table(org,sample_list)
       

    def add_sample(self):     

        self.Org_tableWidget.setRowCount(self.Org_tableWidget.rowCount()+1)
        row_index = self.Org_tableWidget.rowCount()-1
        self.sample_list.sort()
        
        for i in range(self.Org_tableWidget.columnCount()):
            comboBox = QtWidgets.QComboBox()
            for t in self.sample_list:
                comboBox.addItem(t)

            comboBox.setCurrentIndex(row_index)
            self.Org_tableWidget.setCellWidget(row_index, i, comboBox)
        
    def selectedRow(self):
        if self.Org_tableWidget.selectionModel().hasSelection():
            row =  self.Org_tableWidget.selectionModel().selectedIndexes()[0].row()
            return int(row)

    def removeRow(self):
        if self.Org_tableWidget.rowCount() > 0:
            row = self.selectedRow()
            Org_tableWidget.removeRow(row)

    def show_Info_Menu(self, event):
       
        menu = QtWidgets.QMenu()
        add_Action = QAction(QIcon.fromTheme("add"), 'Add sample', self)
        add_Action.triggered.connect(lambda: self.add_sample)

        delete_Action = QAction(QIcon.fromTheme("edit-delete"), 'Delete sample', self)
        delete_Action.triggered.connect(lambda: self.removeRow)
       
        menu.addAction(add_Action)
        menu.addAction(delete_Action)
        menu.popup(QCursor.pos())

        action = menu.exec_()

        if action == add_Action:
            self.add_sample()
        elif action == delete_Action:
            index = self.Org_tableWidget.selectedIndexes()
            self.Org_tableWidget.removeRow(index[0].row())

    def cancel_table(self):

        msg = QtWidgets.QMessageBox()
        msg.setWindowTitle("Cancel table")
        msg.setText("Do you want to reset sample organization?")
        msg.setIcon(msg.Question)  
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel);
        x = msg.exec_()
        if x == QMessageBox.Ok:

            labels = [ self.Org_tableWidget.horizontalHeaderItem(index).text() for index in range(self.Org_tableWidget.columnCount())]
            self.Org_tableWidget.clear()
            self.Org_tableWidget.setHorizontalHeaderLabels(labels)
            self.Org_tableWidget.setRowCount(0)

    def accept_table(self):
        self.sample_organization = {}
        for step in self.samples.keys():
            self.sample_organization[step] = {}

            for rowindex in range(self.Org_tableWidget.rowCount()):
                
                if self.org == 'only cases':
                    sample_id = self.Org_tableWidget.cellWidget(rowindex,0).currentText()
                    case_id = self.Org_tableWidget.cellWidget(rowindex,1).currentText()
                    if case_id in self.samples[step].keys():
                        self.sample_organization[step][sample_id]={"case":self.samples[step][case_id]}
                    else:
                        pass
                    
                elif self.org == 'case-control':
                    sample_id = self.Org_tableWidget.cellWidget(rowindex,0).currentText()
                    case_id = self.Org_tableWidget.cellWidget(rowindex,1).currentText()
                    control_id = self.Org_tableWidget.cellWidget(rowindex,2).currentText()
                    if case_id in self.samples[step].keys():
                        self.sample_organization[step][sample_id]={
                        "case":self.samples[step][case_id],
                        "control":self.samples[step][control_id]}
                    else:
                        pass

                elif self.org == 'trio':
                    sample_id = self.Org_tableWidget.cellWidget(rowindex,0).currentText()
                    case_id = self.Org_tableWidget.cellWidget(rowindex,1).currentText()
                    parent1_id = self.Org_tableWidget.cellWidget(rowindex,2).currentText()
                    parent2_id = self.Org_tableWidget.cellWidget(rowindex,3).currentText()
                    if case_id in self.samples[step].keys():
                        self.sample_organization[step][sample_id]={
                            "case":self.samples[step][case_id],
                            "parent1":self.samples[step][parent1_id],
                            "parent2":self.samples[step][parent2_id]}
                    else:
                        pass
        self.close()
