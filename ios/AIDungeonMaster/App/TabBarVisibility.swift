import SwiftUI

/// Shared state for showing/hiding the custom tab bar (e.g. hidden inside RoomView).
final class TabBarVisibility: ObservableObject {
    @Published var isHidden = false
}
