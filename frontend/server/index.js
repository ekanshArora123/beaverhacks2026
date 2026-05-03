import express from 'express';
import multer from 'multer';
import cors from 'cors';
import path from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = 3001;

// Enable CORS
app.use(cors());
app.use(express.json());

// Ensure uploads directory exists
const uploadsDir = path.join(__dirname, '../public/uploads');
if (!fs.existsSync(uploadsDir)) {
  fs.mkdirSync(uploadsDir, { recursive: true });
}

// Configure multer for image uploads
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, uploadsDir);
  },
  filename: (req, file, cb) => {
    // Use original filename or generate with timestamp
    const uniqueName = `${Date.now()}-${file.originalname}`;
    cb(null, uniqueName);
  }
});

const upload = multer({
  storage: storage,
  fileFilter: (req, file, cb) => {
    // Accept images only
    if (!file.mimetype.startsWith('image/')) {
      return cb(new Error('Only image files are allowed!'), false);
    }
    cb(null, true);
  },
  limits: {
    fileSize: 10 * 1024 * 1024 // 10MB max file size
  }
});

// Endpoint to receive a single image
app.post('/api/upload-image', upload.single('image'), (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: 'No image file provided' });
    }

    const imageUrl = `/uploads/${req.file.filename}`;
    
    console.log(`Image uploaded: ${req.file.filename}`);
    
    res.json({
      success: true,
      message: 'Image uploaded successfully',
      filename: req.file.filename,
      url: imageUrl,
      size: req.file.size
    });
  } catch (error) {
    console.error('Upload error:', error);
    res.status(500).json({ error: 'Failed to upload image' });
  }
});

// Endpoint to receive multiple images
app.post('/api/upload-images', upload.array('images', 10), (req, res) => {
  try {
    if (!req.files || req.files.length === 0) {
      return res.status(400).json({ error: 'No image files provided' });
    }

    const uploadedFiles = req.files.map(file => ({
      filename: file.filename,
      url: `/uploads/${file.filename}`,
      size: file.size
    }));

    console.log(`${req.files.length} images uploaded`);

    res.json({
      success: true,
      message: `${req.files.length} images uploaded successfully`,
      files: uploadedFiles
    });
  } catch (error) {
    console.error('Upload error:', error);
    res.status(500).json({ error: 'Failed to upload images' });
  }
});

// Endpoint to update specific image slots (example1 or example2)
app.post('/api/update-image/:slot', upload.single('image'), (req, res) => {
  try {
    const { slot } = req.params;
    
    if (!['example1', 'example2'].includes(slot)) {
      return res.status(400).json({ error: 'Invalid slot. Use "example1" or "example2"' });
    }

    if (!req.file) {
      return res.status(400).json({ error: 'No image file provided' });
    }

    // Save to specific filename in public directory
    const targetPath = path.join(__dirname, '../public', `${slot}.png`);
    const sourcePath = req.file.path;

    // Copy uploaded file to target location
    fs.copyFileSync(sourcePath, targetPath);

    console.log(`Updated ${slot}.png`);

    res.json({
      success: true,
      message: `${slot}.png updated successfully`,
      filename: `${slot}.png`,
      url: `/${slot}.png`
    });
  } catch (error) {
    console.error('Update error:', error);
    res.status(500).json({ error: 'Failed to update image' });
  }
});

// Health check endpoint
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', message: 'Server is running' });
});

// Get list of uploaded images
app.get('/api/images', (req, res) => {
  try {
    const files = fs.readdirSync(uploadsDir);
    const images = files
      .filter(file => /\.(jpg|jpeg|png|gif|webp)$/i.test(file))
      .map(file => ({
        filename: file,
        url: `/uploads/${file}`
      }));

    res.json({
      count: images.length,
      images: images
    });
  } catch (error) {
    res.status(500).json({ error: 'Failed to list images' });
  }
});

app.listen(PORT, () => {
  console.log(`🚀 Image upload server running on http://localhost:${PORT}`);
  console.log(`📁 Uploads directory: ${uploadsDir}`);
  console.log('\nAvailable endpoints:');
  console.log(`  POST http://localhost:${PORT}/api/upload-image - Upload single image`);
  console.log(`  POST http://localhost:${PORT}/api/upload-images - Upload multiple images`);
  console.log(`  POST http://localhost:${PORT}/api/update-image/:slot - Update example1 or example2`);
  console.log(`  GET  http://localhost:${PORT}/api/images - List all uploaded images`);
  console.log(`  GET  http://localhost:${PORT}/api/health - Health check`);
});
