import QtQuick
import QtQuick.Controls
import QtMultimedia


Item {
    id: root

    width: 420
    height: 420

    property url videoSource: Qt.resolvedUrl("../../../../../assets/monk_hologram_square_layout_sway.mp4")
    property bool showStatusText: true
    property bool autoPlay: true
    property bool muted: true

    // 组件视觉参数
    property color backgroundColor: "black"
    property color textColor: "#D6D9E0"
    property real videoScale: 1.0
    property int radius: 0

    signal clicked()

    function play() {
        player.play()
    }

    function pause() {
        player.pause()
    }

    function restart() {
        player.stop()
        player.play()
    }

    Rectangle {
        anchors.fill: parent
        color: root.backgroundColor
        radius: root.radius
        clip: true

        MediaPlayer {
            id: player
            source: root.videoSource
            loops: MediaPlayer.Infinite
            audioOutput: AudioOutput {
                volume: root.muted ? 0 : 1
            }
            videoOutput: videoOutput

            Component.onCompleted: {
                if (root.autoPlay) {
                    player.play()
                }
            }
        }

        VideoOutput {
            id: videoOutput
            anchors.centerIn: parent
            width: parent.width * root.videoScale
            height: parent.height * root.videoScale
            fillMode: VideoOutput.PreserveAspectFit
            antialiasing: true
        }

        Text {
            visible: root.showStatusText
            text: root.statusText
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: Math.max(10, parent.height * 0.045)
            color: root.textColor
            font.pixelSize: Math.max(14, parent.height * 0.045)
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }

        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                root.clicked()
                if (player.playbackState === MediaPlayer.PlayingState) {
                    player.pause()
                } else {
                    player.play()
                }
            }
        }
    }
}
