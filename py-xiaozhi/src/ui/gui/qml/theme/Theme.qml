// Shared QML theme values.
pragma Singleton
import QtQuick

QtObject {
    id: theme

    // Responsive breakpoints
    readonly property int breakpointSm: 480
    readonly property int breakpointMd: 768
    readonly property int breakpointLg: 1024

    // Updated by AppWindow.
    property int windowWidth: 800

    readonly property real scaleFactor: {
        if (windowWidth < breakpointSm) return 0.8
        if (windowWidth < breakpointMd) return 0.9
        return 1.0
    }

    // Colors
    readonly property color primary: "#3B82F6"
    readonly property color primaryHover: "#60A5FA"
    readonly property color primaryPressed: "#2563EB"
    readonly property color primaryLight: "#0B2447"
    readonly property color primaryText: "#93C5FD"

    readonly property color success: "#00B42A"
    readonly property color successLight: "#052E16"
    readonly property color successBorder: "#166534"

    readonly property color warning: "#FF7D00"
    readonly property color warningLight: "#451A03"
    readonly property color warningBorder: "#92400E"

    readonly property color error: "#F53F3F"
    readonly property color errorHover: "#FF7875"
    readonly property color errorLight: "#450A0A"
    readonly property color errorBorder: "#991B1B"

    readonly property color background: "#000000"
    readonly property color backgroundSecondary: "#111111"
    readonly property color backgroundHover: "#1F1F1F"

    readonly property color textPrimary: "#F9FAFB"
    readonly property color textSecondary: "#D1D5DB"
    readonly property color textPlaceholder: "#6B7280"
    readonly property color textTertiary: "#9CA3AF"

    readonly property color border: "#2A2A2A"
    readonly property color divider: "#1A1A1A"

    // Typography
    readonly property int fontSizeXs: Math.round(10 * scaleFactor)
    readonly property int fontSizeSm: Math.round(12 * scaleFactor)
    readonly property int fontSizeMd: Math.round(14 * scaleFactor)
    readonly property int fontSizeLg: Math.round(16 * scaleFactor)
    readonly property int fontSizeXl: Math.round(20 * scaleFactor)
    readonly property int fontSizeXxl: Math.round(24 * scaleFactor)

    // Spacing
    readonly property int spacingXs: Math.round(4 * scaleFactor)
    readonly property int spacingSm: Math.round(8 * scaleFactor)
    readonly property int spacingMd: Math.round(12 * scaleFactor)
    readonly property int spacingLg: Math.round(16 * scaleFactor)
    readonly property int spacingXl: Math.round(20 * scaleFactor)
    readonly property int spacingXxl: Math.round(24 * scaleFactor)

    // Radius
    readonly property int radiusSm: 4
    readonly property int radiusMd: 8
    readonly property int radiusLg: 12
    readonly property int radiusXl: 16

    // Shadow
    readonly property color shadowColor: "#80000000"
    readonly property color shadowLight: "#50000000"
    readonly property color shadowMedium: "#40000000"
    readonly property color shadowSubtle: "#30000000"
    readonly property int shadowRadius: 12

    // Animation
    readonly property int animationFast: 150
    readonly property int animationNormal: 200
    readonly property int animationSlow: 300

    // Window
    readonly property int windowRadius: 8
    readonly property int titleBarHeight: Math.round(40 * scaleFactor)
    readonly property int resizeMargin: 8

    // Fonts
    readonly property string fontFamily: Qt.platform.os === "osx" ? "PingFang SC" : (Qt.platform.os === "windows" ? "Microsoft YaHei UI" : "sans-serif")
    readonly property string fontFamilyMono: Qt.platform.os === "osx" ? "SF Mono" : "monospace"

    // Platform
    readonly property string currentPlatform: Qt.platform.os
    readonly property bool isMacOS: Qt.platform.os === "osx"
    readonly property bool isWindows: Qt.platform.os === "windows"
    readonly property bool isLinux: Qt.platform.os === "linux"
    readonly property bool titleButtonsOnLeft: isMacOS
}
