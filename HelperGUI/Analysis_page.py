from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
#from os.path import expanduser
import os.path
import subprocess



class Analysis_page(QtWidgets.QWidget):
    def __init__(self, parent = None):
        super(Analysis_page, self).__init__(parent)
        self.setupUi()



    def setupUi(self):
        self.setObjectName("Analysis_page")
        self.resize(935, 869)

        self.gridLayout_2 = QtWidgets.QGridLayout(self)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.frame_2 = QtWidgets.QFrame(self)
        self.frame_2.setMaximumSize(QtCore.QSize(16777215, 101))
        self.frame_2.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame_2.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame_2.setObjectName("frame_2")  
        self.verticalLayout = QtWidgets.QVBoxLayout(self.frame_2)
        self.verticalLayout.setObjectName("verticalLayout")
        self.pushButton = QtWidgets.QPushButton(self.frame_2)
        self.pushButton.setMinimumSize(QtCore.QSize(0, 51))
        self.pushButton.setMaximumSize(QtCore.QSize(16777215, 71))
        self.pushButton.setObjectName("pushButton")
        self.verticalLayout.addWidget(self.pushButton)
        self.gridLayout_2.addWidget(self.frame_2, 4, 0, 1, 1)

        self.frame_3 = QtWidgets.QFrame(self)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame_3.sizePolicy().hasHeightForWidth())
        self.frame_3.setSizePolicy(sizePolicy)
        self.frame_3.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame_3.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame_3.setObjectName("frame_3")
        self.verticalLayout_3 = QtWidgets.QVBoxLayout(self.frame_3)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.label_10 = QtWidgets.QLabel(self.frame_3)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_10.sizePolicy().hasHeightForWidth())
        self.label_10.setSizePolicy(sizePolicy)
        font = QtGui.QFont()
        #font.setFamily("DejaVu Serif Condensed")
        font.setPointSize(30)
        self.label_10.setFont(font)
        self.label_10.setTextFormat(QtCore.Qt.AutoText)
        self.label_10.setAlignment(QtCore.Qt.AlignCenter)
        self.label_10.setObjectName("label_10")
        self.verticalLayout_3.addWidget(self.label_10)
        self.gridLayout_2.addWidget(self.frame_3, 0, 0, 1, 1)
        self.frame = QtWidgets.QFrame(self)
        self.frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame.setObjectName("frame")
        self.gridLayout_3 = QtWidgets.QGridLayout(self.frame)
        self.gridLayout_3.setObjectName("gridLayout_3")
        self.frame_21 = QtWidgets.QFrame(self.frame)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame_21.sizePolicy().hasHeightForWidth())
        self.frame_21.setSizePolicy(sizePolicy)
        self.frame_21.setObjectName("frame_21")
        self.formLayout_2 = QtWidgets.QFormLayout(self.frame_21)
        self.formLayout_2.setObjectName("formLayout_2")
        self.treeWidget = QtWidgets.QTreeWidget(self.frame_21)
        self.treeWidget.setEnabled(True)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(1)
        sizePolicy.setHeightForWidth(self.treeWidget.sizePolicy().hasHeightForWidth())
        self.treeWidget.setSizePolicy(sizePolicy)
        self.treeWidget.setMinimumSize(QtCore.QSize(461, 548))
        self.treeWidget.setMaximumSize(QtCore.QSize(16777215, 16777215))
        self.treeWidget.setAcceptDrops(False)
        self.treeWidget.setAutoFillBackground(True)
        self.treeWidget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.treeWidget.setTextElideMode(QtCore.Qt.ElideRight)
        self.treeWidget.setAutoExpandDelay(-1)
        self.treeWidget.setIndentation(20)
        self.treeWidget.setRootIsDecorated(True)
        self.treeWidget.setAnimated(True)
        self.treeWidget.setAllColumnsShowFocus(False)
        self.treeWidget.setHeaderHidden(False)
        self.treeWidget.setColumnCount(1)
        self.treeWidget.setObjectName("treeWidget")

        self.item_pre_alig = QtWidgets.QTreeWidgetItem(self.treeWidget)
        self.item_pre_alig.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsTristate|self.item_pre_alig.flags())
        self.item_adapt = QtWidgets.QTreeWidgetItem(self.item_pre_alig)
        self.item_adapt.setFlags(self.item_adapt.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_adapt.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_len_filt = QtWidgets.QTreeWidgetItem(self.item_pre_alig)
        self.item_len_filt.setFlags(self.item_len_filt.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_len_filt.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_q_filt = QtWidgets.QTreeWidgetItem(self.item_pre_alig)
        self.item_q_filt.setFlags(self.item_q_filt.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_q_filt.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_fq_qc = QtWidgets.QTreeWidgetItem(self.item_pre_alig)
        self.item_fq_qc.setFlags(self.item_fq_qc.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_fq_qc.setCheckState(0, QtCore.Qt.Unchecked)

        self.item_align = QtWidgets.QTreeWidgetItem(self.treeWidget)
        self.item_align.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsTristate|self.item_align.flags())      
        self.item_umi = QtWidgets.QTreeWidgetItem(self.item_align)
        self.item_umi.setFlags(self.item_umi.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_umi.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_alig = QtWidgets.QTreeWidgetItem(self.item_align)
        self.item_alig.setFlags(self.item_alig.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_alig.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_sambam = QtWidgets.QTreeWidgetItem(self.item_align)
        self.item_sambam.setFlags(self.item_sambam.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_sambam.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_sort = QtWidgets.QTreeWidgetItem(self.item_align)
        self.item_sort.setFlags(self.item_sort.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_sort.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_bam_qc = QtWidgets.QTreeWidgetItem(self.item_align)
        self.item_bam_qc.setFlags(self.item_bam_qc.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_bam_qc.setCheckState(0, QtCore.Qt.Unchecked)

        self.item_pre_proc = QtWidgets.QTreeWidgetItem(self.treeWidget)
        self.item_pre_proc.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsTristate|self.item_pre_proc.flags())      
       
        self.item_bam_filt = QtWidgets.QTreeWidgetItem(self.item_pre_proc)
        self.item_bam_filt.setFlags(self.item_bam_qc.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_bam_filt.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_rgroup = QtWidgets.QTreeWidgetItem(self.item_pre_proc)
        self.item_rgroup.setFlags(self.item_rgroup.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_rgroup.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_dup = QtWidgets.QTreeWidgetItem(self.item_pre_proc)
        self.item_dup.setFlags(self.item_dup.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_dup.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_realig = QtWidgets.QTreeWidgetItem(self.item_pre_proc)
        self.item_realig.setFlags(self.item_realig.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_realig.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_bqsr = QtWidgets.QTreeWidgetItem(self.item_pre_proc)
        self.item_bqsr.setFlags(self.item_bqsr.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_bqsr.setCheckState(0, QtCore.Qt.Unchecked)

        self.item_vcalling = QtWidgets.QTreeWidgetItem(self.treeWidget)     
        self.item_vcalling.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsTristate|self.item_vcalling.flags())      
    
        self.item_shortv_call = QtWidgets.QTreeWidgetItem(self.item_vcalling)
        self.item_shortv_call.setFlags(self.item_shortv_call.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_shortv_call.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_cnv_call = QtWidgets.QTreeWidgetItem(self.item_vcalling)
        self.item_cnv_call.setFlags(self.item_cnv_call.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_cnv_call.setCheckState(0, QtCore.Qt.Unchecked)

        self.item_post_proc = QtWidgets.QTreeWidgetItem(self.treeWidget)     
        self.item_post_proc.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsTristate|self.item_post_proc.flags())      
    
        self.item_vcf_norm = QtWidgets.QTreeWidgetItem(self.item_post_proc)
        self.item_vcf_norm.setFlags(self.item_vcf_norm.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_vcf_norm.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_vcf_filt = QtWidgets.QTreeWidgetItem(self.item_post_proc)
        self.item_vcf_filt.setFlags(self.item_vcf_filt.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_vcf_filt.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_vcf_to_tsv = QtWidgets.QTreeWidgetItem(self.item_post_proc)
        self.item_vcf_to_tsv.setFlags(self.item_vcf_to_tsv.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_vcf_to_tsv.setCheckState(0, QtCore.Qt.Unchecked)

        self.item_ann = QtWidgets.QTreeWidgetItem(self.treeWidget)     
        self.item_ann.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsTristate|self.item_ann.flags())      
    
        self.item_shortv_ann = QtWidgets.QTreeWidgetItem(self.item_ann)
        self.item_shortv_ann.setFlags(self.item_shortv_ann.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_shortv_ann.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_cnv_ann = QtWidgets.QTreeWidgetItem(self.item_ann)
        self.item_cnv_ann.setFlags(self.item_cnv_ann.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_cnv_ann.setCheckState(0, QtCore.Qt.Unchecked)

        self.item_postann = QtWidgets.QTreeWidgetItem(self.treeWidget)     
        self.item_postann.setFlags(QtCore.Qt.ItemIsSelectable|QtCore.Qt.ItemIsDragEnabled|QtCore.Qt.ItemIsDropEnabled|QtCore.Qt.ItemIsUserCheckable|QtCore.Qt.ItemIsEnabled|QtCore.Qt.ItemIsTristate|self.item_postann.flags())      
        
        self.item_filt_ann = QtWidgets.QTreeWidgetItem(self.item_postann)
        self.item_filt_ann.setFlags(self.item_filt_ann.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_filt_ann.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_trs_filt_ann = QtWidgets.QTreeWidgetItem(self.item_postann)
        self.item_trs_filt_ann.setFlags(self.item_trs_filt_ann.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_trs_filt_ann.setCheckState(0, QtCore.Qt.Unchecked)
        self.item_vcf_ann_to_tsv = QtWidgets.QTreeWidgetItem(self.item_postann)
        self.item_vcf_ann_to_tsv.setFlags(self.item_cnv_ann.flags() | QtCore.Qt.ItemIsUserCheckable)
        self.item_vcf_ann_to_tsv.setCheckState(0, QtCore.Qt.Unchecked)

        self.treeWidget.header().setVisible(True)
        self.treeWidget.header().setCascadingSectionResizes(True)
        self.treeWidget.header().setDefaultSectionSize(300)
        self.treeWidget.header().setHighlightSections(False)
        self.treeWidget.header().setMinimumSectionSize(100)
        self.treeWidget.header().setSortIndicatorShown(False)
        self.treeWidget.header().setStretchLastSection(True)
        self.formLayout_2.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.treeWidget)

        self.gridLayout_3.addWidget(self.frame_21, 0, 1, 2, 1)
        self.frame_5 = QtWidgets.QFrame(self.frame)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame_5.sizePolicy().hasHeightForWidth())
        self.frame_5.setSizePolicy(sizePolicy)
        self.frame_5.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame_5.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame_5.setObjectName("frame_5")
        self.verticalLayout_4 = QtWidgets.QVBoxLayout(self.frame_5)
        self.verticalLayout_4.setObjectName("verticalLayout_4")
        self.groupBox = QtWidgets.QGroupBox(self.frame_5)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.groupBox.sizePolicy().hasHeightForWidth())
        self.groupBox.setSizePolicy(sizePolicy)
        self.groupBox.setAlignment(QtCore.Qt.AlignCenter)
        self.groupBox.setObjectName("groupBox")
        self.formLayout = QtWidgets.QFormLayout(self.groupBox)
        self.formLayout.setObjectName("formLayout")
        self.label = QtWidgets.QLabel(self.groupBox)
        self.label.setObjectName("label")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.label)
        self.lineEdit = QtWidgets.QLineEdit(self.groupBox)
        self.lineEdit.setObjectName("lineEdit")
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.lineEdit)
        self.label_2 = QtWidgets.QLabel(self.groupBox)
        self.label_2.setObjectName("label_2")
        self.formLayout.setWidget(2, QtWidgets.QFormLayout.LabelRole, self.label_2)
        self.comboBox = QtWidgets.QComboBox(self.groupBox)
        self.comboBox.setObjectName("comboBox")
        self.comboBox.addItem("")
        self.comboBox.addItem("")
        self.comboBox.addItem("")
        self.comboBox.addItem("")
        self.comboBox.addItem("")
        self.comboBox.addItem("")
        self.comboBox.addItem("")
        self.formLayout.setWidget(2, QtWidgets.QFormLayout.FieldRole, self.comboBox)
        self.label_3 = QtWidgets.QLabel(self.groupBox)
        self.label_3.setObjectName("label_3")
        self.formLayout.setWidget(3, QtWidgets.QFormLayout.LabelRole, self.label_3)
        self.comboBox_2 = QtWidgets.QComboBox(self.groupBox)
        self.comboBox_2.setObjectName("comboBox_2")
        self.comboBox_2.addItem("")
        self.comboBox_2.addItem("")
        self.comboBox_2.addItem("")
        self.formLayout.setWidget(3, QtWidgets.QFormLayout.FieldRole, self.comboBox_2)
        self.verticalLayout_4.addWidget(self.groupBox)
        self.groupBox_3 = QtWidgets.QGroupBox(self.frame_5)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.groupBox_3.sizePolicy().hasHeightForWidth())
        self.groupBox_3.setSizePolicy(sizePolicy)
        self.groupBox_3.setAlignment(QtCore.Qt.AlignCenter)
        self.groupBox_3.setObjectName("groupBox_3")
        self.gridLayout = QtWidgets.QGridLayout(self.groupBox_3)
        self.gridLayout.setObjectName("gridLayout")
        self.toolButton_2 = QtWidgets.QToolButton(self.groupBox_3)
        self.toolButton_2.setObjectName("toolButton_2")
        self.gridLayout.addWidget(self.toolButton_2, 2, 2, 1, 1)
        self.toolButton_3 = QtWidgets.QToolButton(self.groupBox_3)
        self.toolButton_3.setObjectName("toolButton_3")
        self.gridLayout.addWidget(self.toolButton_3, 3, 2, 1, 1)
        self.label_6 = QtWidgets.QLabel(self.groupBox_3)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_6.sizePolicy().hasHeightForWidth())
        self.label_6.setSizePolicy(sizePolicy)
        self.label_6.setObjectName("label_6")
        self.gridLayout.addWidget(self.label_6, 3, 0, 1, 1)
        self.label_5 = QtWidgets.QLabel(self.groupBox_3)
        self.label_5.setObjectName("label_5")
        self.gridLayout.addWidget(self.label_5, 2, 0, 1, 1)
        self.toolButton = QtWidgets.QToolButton(self.groupBox_3)
        self.toolButton.setObjectName("toolButton")
        self.gridLayout.addWidget(self.toolButton, 1, 2, 1, 1)
        self.lineEdit_3 = QtWidgets.QLineEdit(self.groupBox_3)
        self.lineEdit_3.setObjectName("lineEdit_3")
        self.gridLayout.addWidget(self.lineEdit_3, 2, 1, 1, 1)
        self.label_4 = QtWidgets.QLabel(self.groupBox_3)
        self.label_4.setObjectName("label_4")
        self.gridLayout.addWidget(self.label_4, 1, 0, 1, 1)
        self.lineEdit_2 = QtWidgets.QLineEdit(self.groupBox_3)
        self.lineEdit_2.setObjectName("lineEdit_2")
        self.gridLayout.addWidget(self.lineEdit_2, 1, 1, 1, 1)
        self.lineEdit_4 = QtWidgets.QLineEdit(self.groupBox_3)
        self.lineEdit_4.setObjectName("lineEdit_4")
        self.gridLayout.addWidget(self.lineEdit_4, 3, 1, 1, 1)
        self.verticalLayout_4.addWidget(self.groupBox_3)
        self.frame_4 = QtWidgets.QFrame(self.frame_5)
        self.frame_4.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame_4.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame_4.setObjectName("frame_4")
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(self.frame_4)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.textBrowser = QtWidgets.QTextBrowser(self.frame_4)
        self.textBrowser.setObjectName("textBrowser")
        self.verticalLayout_2.addWidget(self.textBrowser)
        self.frame_6 = QtWidgets.QFrame(self.frame_4)
        self.frame_6.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.frame_6.setFrameShadow(QtWidgets.QFrame.Raised)
        self.frame_6.setObjectName("frame_6")
        self.horizontalLayout = QtWidgets.QHBoxLayout(self.frame_6)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.pushButton_3 = QtWidgets.QPushButton(self.frame_6)
        self.pushButton_3.setObjectName("pushButton_3")
        self.horizontalLayout.addWidget(self.pushButton_3)
        self.pushButton_2 = QtWidgets.QPushButton(self.frame_6)
        self.pushButton_2.setObjectName("pushButton_2")
        self.horizontalLayout.addWidget(self.pushButton_2)
        self.verticalLayout_2.addWidget(self.frame_6)
        self.verticalLayout_4.addWidget(self.frame_4)
        self.gridLayout_3.addWidget(self.frame_5, 0, 0, 1, 1)
        self.gridLayout_2.addWidget(self.frame, 1, 0, 1, 1)

        self.retranslateUi()
        QtCore.QMetaObject.connectSlotsByName(self)

    def retranslateUi(self):
        _translate = QtCore.QCoreApplication.translate
        self.setWindowTitle(_translate("Analysis_page", "Analysis Settings"))
        self.pushButton.setText(_translate("Analysis_page", "Start POWERCALL V2.0"))
        self.label_10.setText(_translate("Analysis_page", "Analysis Settings"))
        self.treeWidget.headerItem().setText(0, _translate("Analysis_page", "Analysis Steps"))
        __sortingEnabled = self.treeWidget.isSortingEnabled()
        self.treeWidget.setSortingEnabled(False)
        self.treeWidget.topLevelItem(0).setText(0, _translate("Analysis_page", "Pre-Alignment"))
        self.treeWidget.topLevelItem(0).child(0).setText(0, _translate("Analysis_page", "Adapters trimming"))
        self.treeWidget.topLevelItem(0).child(1).setText(0, _translate("Analysis_page", "FASTQ read lenght filter"))
        self.treeWidget.topLevelItem(0).child(2).setText(0, _translate("Analysis_page", "FASTQ quality filter"))
        self.treeWidget.topLevelItem(0).child(3).setText(0, _translate("Analysis_page", "FASTQ quality control"))
        self.treeWidget.topLevelItem(1).setText(0, _translate("Analysis_page", "Alignment"))
        self.treeWidget.topLevelItem(1).child(0).setText(0, _translate("Analysis_page", "UMI/Molecular barcodes merge"))
        self.treeWidget.topLevelItem(1).child(1).setText(0, _translate("Analysis_page", "FASTQ alignment"))
        self.treeWidget.topLevelItem(1).child(2).setText(0, _translate("Analysis_page", "SAM to BAM convertion"))
        self.treeWidget.topLevelItem(1).child(3).setText(0, _translate("Analysis_page", "BAM sort"))
        self.treeWidget.topLevelItem(1).child(4).setText(0, _translate("Analysis_page", "BAM quality control"))
        self.treeWidget.topLevelItem(2).setText(0, _translate("Analysis_page", "Pre-Processing"))
        self.treeWidget.topLevelItem(2).child(0).setText(0, _translate("Analysis_page", "BAM filter"))
        self.treeWidget.topLevelItem(2).child(1).setText(0, _translate("Analysis_page", "Add readgroups to BAM"))
        self.treeWidget.topLevelItem(2).child(2).setText(0, _translate("Analysis_page", "PCR duplicates marking"))
        self.treeWidget.topLevelItem(2).child(3).setText(0, _translate("Analysis_page", "InDels realignment"))
        self.treeWidget.topLevelItem(2).child(4).setText(0, _translate("Analysis_page", "Base quality recalibration"))
        self.treeWidget.topLevelItem(3).setText(0, _translate("Analysis_page", "Variant Calling"))
        self.treeWidget.topLevelItem(3).child(0).setText(0, _translate("Analysis_page", "SNV & short InDels"))
        self.treeWidget.topLevelItem(3).child(1).setText(0, _translate("Analysis_page", "Copy Number Variation"))
        self.treeWidget.topLevelItem(4).setText(0, _translate("Analysis_page", "Post-Processing"))
        self.treeWidget.topLevelItem(4).child(0).setText(0, _translate("Analysis_page", "VCF filter"))
        self.treeWidget.topLevelItem(4).child(1).setText(0, _translate("Analysis_page", "Hard filter"))
        self.treeWidget.topLevelItem(4).child(2).setText(0, _translate("Analysis_page", "VCF to TSV convertion"))
        self.treeWidget.topLevelItem(5).setText(0, _translate("Analysis_page", "Annotation"))
        self.treeWidget.topLevelItem(5).child(0).setText(0, _translate("Analysis_page", "SNV & short InDels"))
        self.treeWidget.topLevelItem(5).child(1).setText(0, _translate("Analysis_page", "Copy Number Variation"))
        self.treeWidget.topLevelItem(6).setText(0, _translate("Add_tags", "Post-Annotation"))
        self.treeWidget.topLevelItem(6).child(0).setText(0, _translate("Analysis_page", "Annotation filter"))
        self.treeWidget.topLevelItem(6).child(2).setText(0, _translate("Analysis_page", "Annotated VCF to TSV convertion"))
        self.treeWidget.topLevelItem(6).child(1).setText(0, _translate("Analysis_page", "Ann transcripts filter"))
        self.treeWidget.setSortingEnabled(__sortingEnabled)
        self.groupBox.setTitle(_translate("Analysis_page", "Analysis Informations"))
        self.label.setText(_translate("Analysis_page", "Run ID"))
        self.label_2.setText(_translate("Analysis_page", "Panel Name"))

        self.comboBox.setItemText(0, _translate("Analysis_page", "Illumina TrusighCardio"))
        self.comboBox.setItemText(1, _translate("Analysis_page", "Illumina TrusighCancer"))
        self.comboBox.setItemText(2, _translate("Analysis_page", "Illumina TrusighOne"))
        self.comboBox.setItemText(3, _translate("Analysis_page", "SophiaGen HCS"))
        self.comboBox.setItemText(4, _translate("Analysis_page", "Agilent CardioV1"))
        self.comboBox.setItemText(5, _translate("Analysis_page", "Agilent AneurysmV1"))
        self.comboBox.setItemText(6, _translate("Analysis_page", "Agilent CancerV1"))

        self.label_3.setText(_translate("Analysis_page", "Pipeline"))

        self.comboBox_2.setItemText(0, _translate("Analysis_page", "Germline"))
        self.comboBox_2.setItemText(1, _translate("Analysis_page", "Somatic"))
        self.comboBox_2.setItemText(2, _translate("Analysis_page", "Cellfree"))
        
        #self.groupBox_3.setTitle(_translate("Analysis_page", "Analysis Paths"))
        self.toolButton_2.setText(_translate("Analysis_page", "..."))
        self.toolButton_3.setText(_translate("Analysis_page", "..."))
        self.label_6.setText(_translate("Analysis_page", "Tools config file"))
        self.label_5.setText(_translate("Analysis_page", "Working directory"))
        self.toolButton.setText(_translate("Analysis_page", "..."))
        self.label_4.setText(_translate("Analysis_page", "Samplesheet"))
        self.pushButton_3.setText(_translate("Analysis_page", "Remove"))
        self.pushButton_2.setText(_translate("Analysis_page", "Add to Queue"))



    def getsamplesheet(self):
        ss_options = QFileDialog.Options()
        ss_options |= QFileDialog.DontUseNativeDialog
        ss, _ = QFileDialog.getOpenFileName(self,"Choose Samplesheet", "~","Sample sheet files (*.samplesheet *.ss)", options=ss_options)
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
        folder = QFileDialog.getExistingDirectory(self,"Choose Working dir", "~" , options=wdir_options)
        if folder:
            self.workDir_lineEdit.setStyleSheet("color: black;")
            self.workDir_lineEdit.setText(folder)

    

    def get_workflow(self):
        workflow = ''

        if self.item_pre_alig.checkState(0) != 0: workflow += ["prealignment"]
        if self.item_align.checkState(0) != 0: workflow += ["alignment"]
        if self.item_pre_proc.checkState(0) != 0: workflow += ["preprocessing"]
        #if self.item_vcalling.checkState(0) != 0: workflow += ["variant_calling"]
        if self.item_post_proc.checkState(0) != 0: workflow += ["postprocessing"]
        if self.item_ann.checkState(0) != 0: workflow += ["annotation"]
        if self.item_postann.checkState(0) != 0: workflow += ["postannotation"]

        if self.item_adapt.checkState(0) == 2: workflow += ["trim_adapters"]
        if self.item_len_filt.checkState(0) == 2: workflow += ["filter_fastq"]
        if self.item_q_filt.checkState(0) == 2: workflow += ["filter_fastq"]
        if self.item_fq_qc.checkState(0) == 2: workflow += ["fastq_QC"]
        if self.item_umi.checkState(0) == 2: workflow += ["merge_UMI"]
        if self.item_alig.checkState(0) == 2: workflow += ["fastq_alignment"]
        if self.item_sambam.checkState(0) == 2: workflow += ["sam_to_bam"]
        if self.item_sort.checkState(0) == 2: workflow += ["sortSam"]
        if self.item_bam_qc.checkState(0) == 2: workflow += ["bam_QC"]
        if self.item_bam_filt.checkState(0) == 2: workflow += ["filter_bam"]
        if self.item_rgroup.checkState(0) == 2: workflow += ["add_readgroups"]
        if self.item_dup.checkState(0) == 2: workflow += ["mark_pcr_dup"]
        if self.item_realig.checkState(0) == 2: workflow += ["indel_realignment"]
        if self.item_bqsr.checkState(0) == 2: workflow += ["BQ_recalibration"]
        if self.item_shortv_call.checkState(0) == 2: workflow += ["variant_calling"]
        if self.item_cnv_call.checkState(0) == 2: workflow += ["cnv_calling"]
        if self.item_vcf_norm.checkState(0) == 2: workflow += ["vcf_norm"]
        if self.item_vcf_filt.checkState(0) == 2: workflow += ["vcf_filter"]
        if self.item_vcf_to_tsv.checkState(0) == 2: workflow += ["vcf_to_tsv"]
        if self.item_shortv_ann.checkState(0) == 2: workflow += ["variant_ann"]
        if self.item_cnv_ann.checkState(0) == 2: workflow += ["cnv_ann"]
        if self.item_filt_ann.checkState(0) == 2: workflow += ["ann_filter"]
        if self.item_trs_filt_ann.checkState(0) == 2: workflow += ["trs_filter"]
        if self.item_vcf_ann_to_tsv.checkState(0) == 2: workflow += ["ann_vcf_to_tsv"]

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