import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { LobbyPage } from './pages/LobbyPage';
import { RoomPage } from './pages/RoomPage';
import { SinglePlayerPage } from './pages/SinglePlayerPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LobbyPage />} />
        <Route path="/play" element={<SinglePlayerPage />} />
        <Route path="/room/:roomId" element={<RoomPage />} />
        {/* Catch-all → lobby */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
