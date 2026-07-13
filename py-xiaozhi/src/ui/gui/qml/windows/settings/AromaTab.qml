// 香薰系统配置
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../theme"
import "../../controls"

ScrollView {
    id: root
    clip: true

    ColumnLayout {
        width: root.availableWidth
        spacing: Theme.spacingLg

        Text { text: "香薰系统"; font.pixelSize: Theme.fontSizeXl; font.weight: Font.DemiBold; color: Theme.textPrimary }

        RowLayout {
            Layout.fillWidth: true
            Text { text: "启用香薰硬件"; Layout.fillWidth: true; color: Theme.textSecondary }
            XSwitch {
                checked: settingsModel ? settingsModel.aromaEnabled : false
                onToggled: if (settingsModel) settingsModel.aromaEnabled = checked
            }
        }

        GridLayout {
            Layout.fillWidth: true
            columns: 2
            rowSpacing: Theme.spacingMd
            columnSpacing: Theme.spacingLg

            Text { text: "串口"; color: Theme.textSecondary; Layout.preferredWidth: 120 }
            TextField {
                Layout.fillWidth: true
                text: settingsModel ? settingsModel.aromaSerialPort : ""
                placeholderText: "Linux: /dev/ttyUSB0；Windows: COM3"
                onEditingFinished: if (settingsModel) settingsModel.aromaSerialPort = text
            }

            Text { text: "波特率"; color: Theme.textSecondary; Layout.preferredWidth: 120 }
            XSpinBox {
                Layout.fillWidth: true
                from: 300; to: 115200; stepSize: 300
                value: settingsModel ? settingsModel.aromaBaudrate : 9600
                onValueModified: if (settingsModel) settingsModel.aromaBaudrate = value
            }

            Text { text: "设备地址"; color: Theme.textSecondary; Layout.preferredWidth: 120 }
            XSpinBox {
                Layout.fillWidth: true
                from: 1; to: 247
                value: settingsModel ? settingsModel.aromaDeviceAddress : 1
                onValueModified: if (settingsModel) settingsModel.aromaDeviceAddress = value
            }

            Text { text: "串口超时（秒）"; color: Theme.textSecondary; Layout.preferredWidth: 120 }
            XSpinBox {
                Layout.fillWidth: true; from: 1; to: 30; stepSize: 1
                value: settingsModel ? settingsModel.aromaSerialTimeout : 1
                onValueModified: if (settingsModel) settingsModel.aromaSerialTimeout = value
            }

            Text { text: "重试次数"; color: Theme.textSecondary; Layout.preferredWidth: 120 }
            XSpinBox {
                Layout.fillWidth: true; from: 0; to: 5
                value: settingsModel ? settingsModel.aromaRetries : 1
                onValueModified: if (settingsModel) settingsModel.aromaRetries = value
            }

            Text { text: "有效电平"; color: Theme.textSecondary; Layout.preferredWidth: 120 }
            XSwitch {
                checked: settingsModel ? settingsModel.aromaActiveHigh : true
                onToggled: if (settingsModel) settingsModel.aromaActiveHigh = checked
            }

            Text { text: "配型模式"; color: Theme.textSecondary; Layout.preferredWidth: 120 }
            ComboBox {
                Layout.fillWidth: true
                model: ["binary", "concentration"]
                currentIndex: settingsModel && settingsModel.aromaPatternMode === "concentration" ? 1 : 0
                onActivated: if (settingsModel) settingsModel.aromaPatternMode = currentText
            }

            Text { text: "默认浓度"; color: Theme.textSecondary; Layout.preferredWidth: 120 }
            XSpinBox {
                Layout.fillWidth: true; from: 1; to: 100
                value: settingsModel ? settingsModel.aromaDefaultConcentration : 100
                onValueModified: if (settingsModel) settingsModel.aromaDefaultConcentration = value
            }

            Text { text: "Qwen 接口"; color: Theme.textSecondary; Layout.preferredWidth: 120 }
            TextField {
                Layout.fillWidth: true
                text: settingsModel ? settingsModel.aromaQwenBaseUrl : ""
                onEditingFinished: if (settingsModel) settingsModel.aromaQwenBaseUrl = text
                placeholderText: "OpenAI 兼容接口地址"
            }

            Text { text: "Qwen 模型"; color: Theme.textSecondary; Layout.preferredWidth: 120 }
            TextField {
                Layout.fillWidth: true
                text: settingsModel ? settingsModel.aromaQwenModel : "qwen3.6-plus"
                onEditingFinished: if (settingsModel) settingsModel.aromaQwenModel = text
            }

            Text { text: "Qwen API Key"; color: Theme.textSecondary; Layout.preferredWidth: 120 }
            XTextField {
                Layout.fillWidth: true
                text: settingsModel ? settingsModel.aromaQwenApiKey : ""
                isPassword: true
                onEditingFinished: if (settingsModel) settingsModel.aromaQwenApiKey = text
            }
        }

        Text {
            text: "16路香型映射（JSON，键为香型名称，值必须恰好为1～16）"
            color: Theme.textSecondary
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        TextArea {
            Layout.fillWidth: true
            Layout.preferredHeight: 170
            text: settingsModel ? settingsModel.aromaChannelMap : "{}"
            wrapMode: TextArea.Wrap
            onEditingFinished: if (settingsModel) settingsModel.aromaChannelMap = text
            placeholderText: '{"lavender": 1, "bergamot": 2, ...}'
        }

        Text {
            Layout.fillWidth: true
            text: "保存后重启语音服务；首次接线测试请断开负载，并确认串口、地址、有效电平和16路映射。"
            color: Theme.textPlaceholder
            wrapMode: Text.WordWrap
        }
        Item { Layout.fillHeight: true }
    }
}
