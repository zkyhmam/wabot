const { connectToWhatsApp, setSocket } = require('./controllers/whatsappController');
const http = require('http');
const express = require('express');
const { Server } = require('socket.io');

const app = express();
const server = http.createServer(app);
const io = new Server(server);

io.on('connection', (socket) => {
    console.log('🔌  Socket.IO:  Client connected:', socket.id);
    setSocket(socket);

    socket.on('disconnect', () => {
        console.log('🔌  Socket.IO:  Client disconnected:', socket.id);
    });
});

app.get('/', (req, res) => {
    res.send('Zaky AI Bot is running!');
});

console.log("🚀  Starting WhatsApp connection...");
connectToWhatsApp();

const PORT = process.env.PORT || 9000;
server.listen(PORT, () => {
    console.log(`✅  Server is running on port ${PORT}`);
});
