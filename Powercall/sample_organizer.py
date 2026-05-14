# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '/home/jarvis/git/Powercall2/Powercall/sample_organizer.ui'
#
# Created by: PyQt5 UI code generator 5.14.1
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(400, 300)
        self.formLayout = QtWidgets.QFormLayout(Form)
        self.formLayout.setObjectName("formLayout")
        self.Org_label = QtWidgets.QLabel(Form)
        self.Org_label.setObjectName("Org_label")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.Org_label)
        self.Org_type_label = QtWidgets.QLabel(Form)
        self.Org_type_label.setText("")
        self.Org_type_label.setObjectName("Org_type_label")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.Org_type_label)
        self.Cancel_org_pushButton = QtWidgets.QPushButton(Form)
        self.Cancel_org_pushButton.setObjectName("Cancel_org_pushButton")
        self.formLayout.setWidget(3, QtWidgets.QFormLayout.LabelRole, self.Cancel_org_pushButton)
        self.Accept_pushButton = QtWidgets.QPushButton(Form)
        self.Accept_pushButton.setObjectName("Accept_pushButton")
        self.formLayout.setWidget(3, QtWidgets.QFormLayout.FieldRole, self.Accept_pushButton)
        self.Org_tableWidget = QtWidgets.QTableWidget(Form)
        self.Org_tableWidget.setObjectName("Org_tableWidget")
        self.Org_tableWidget.setColumnCount(0)
        self.Org_tableWidget.setRowCount(0)
        self.formLayout.setWidget(2, QtWidgets.QFormLayout.SpanningRole, self.Org_tableWidget)
        self.Addsample_pushButton = QtWidgets.QPushButton(Form)
        self.Addsample_pushButton.setObjectName("Addsample_pushButton")
        self.formLayout.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.Addsample_pushButton)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _translate = QtCore.QCoreApplication.translate
        Form.setWindowTitle(_translate("Form", "Form"))
        self.Org_label.setText(_translate("Form", "Organization:"))
        self.Cancel_org_pushButton.setText(_translate("Form", "Cancel"))
        self.Accept_pushButton.setText(_translate("Form", "Accept"))
        self.Addsample_pushButton.setText(_translate("Form", "Add Sample"))
