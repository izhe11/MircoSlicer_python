#stylesheet

#QPushButton通用
btnStyle = """
QPushButton {
        background-color: #659a40;
        color: #000000;
        border: none;
        padding: 2px;
        font-size: 15px;
        font-family: Microsoft YaHei UI;
        font-weight: 600;
        border-radius: 9px;
    }
    QPushButton:hover {
        background-color: rgb(255,158,33);
    }
    QPushButton:pressed {
        background-color: rgb(255,158,33);
    }
        """

#标题栏frame style
titleFrameStyle = """
    background-color: #659a40;
    border-top-left-radius: 15px;
    border-top-right-radius: 15px;
"""

#标题文字style
titleBtnStyle = """
QPushButton {
       background-color: #659a40;   
       font-family: Arial;
       font-weight: 600;
       border-radius: 15px;
       font-size: 14px;
       margin-bottom: 4px;
}
"""

#标题栏close mini
titleOperateBtnClose ="""
QPushButton {
       border-top-left-radius: 0px;
       border-top-right-radius: 15px;
}
QPushButton:hover {
        background-color: rgb(136,29,37);
    }

"""
titleOperateBtnMini ="""
QPushButton {
       border-radius: 0px;
}
QPushButton:hover {
        background-color: #D3D3D3;
    }

"""

#参数面板style
paraFrameStyle = """
    background-color: #75409A;
    border-bottom-left-radius: 0px;
    border-bottom-right-radius: 0px;
"""

#参数标签style
paraLabelStyle = """
QLabel {
       background-color: #659a40;   
       font-family: Microsoft YaHei;
       font-weight: 400;
       border-radius: 12px;
       font-size: 12px;
       padding: 2px;
       qproperty-alignment: AlignCenter;
}
"""
#状态标签style
statusStyle = """
QLabel {
       color: #A9A9A9;
       margin-bottom: 0px;
}
"""

#radoibutton样式
radiobtnStyle = """
QRadioButton:hover {
       font-family: Microsoft YaHei;
       font-size: 12px;
}
"""

#group标题字体
groupTitleStyle = """
QGroupBox{
        font-family: Microsoft YaHei;
        font-size: 14px; 
}
QGroupBox::title { 
        font-size: 14px; 
        font-weight: bold; 
}
"""

#lineEdit样式
lineStyle = """
QLineEdit{
        background-color: #D3D3D3;
        border-radius: 12px;
        padding: 2px;
        border: 1px solid #DCDCDC;
        padding-left: 8px;
}
"""

#combox style
comboStyle = """
QComboBox{
        background-color: #D3D3D3;
        border-radius: 11px;
        padding: 2px;
        padding-left: 8px;
        width: 160px;
        border: 1px solid #DCDCDC;
        margin-bottom: 3px;
}
QComboBox::drop-down {
      subcontrol-origin: padding;
      subcontrol-position: top right;
      padding-right: 15px;
      border:none;
  }
QComboBox::down-arrow{
      image:url(downarrow.png)
  }
QComboBox QAbstractItemView {
      border-radius: 0px;
      border: 1px solid #DCDCDC;
      background-color: #D3D3D3;
}
QListView {
    background-color: #F0F8FF;
    border: none;
    outline: none;
    padding: 5px;
}
QListView::item:hover {
    border-radius: 9px;
    background-color: #1E90FF;
}
QListView::item:selected {
    color: #000000;
    outline: 0px;
    border-radius: 9px;
    background-color: rgb(255,158,33);
}
"""

#进度条样式
barStyle = """
QProgressBar {
    height: 12px;
    font-size: 10px;
    border: none;
    border-radius: 6px;
    text-align: center;
    background-color: #A9A9A9;
    margin: 5px;
}
QProgressBar::chunk {
    background-color: #659a40;
    border-radius: 6px;
}
"""

#左键下拉菜单style
menuStyle = """
 QMenu {
     background-color: #D3D3D3; 
     margin: 2px;
 }

 QMenu::item {
     background-color: transparent;
     height: 20px;
     width: 60px;
     padding: 4px;
     border-radius: 10px;
     font-size: 14px;
 }

 QMenu::item:selected { 
     background-color: #1E90FF;
 }
"""

