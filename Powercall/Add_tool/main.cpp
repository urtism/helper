#include "add_tool.h"

#include <QApplication>

int main(int argc, char *argv[])
{
    QApplication a(argc, argv);
    Add_tool w;
    w.show();
    return a.exec();
}
