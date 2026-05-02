# API Testing Guide

## Quick Tests

### 1. Test Server Health

```bash
curl http://localhost:3001/api/health
```

Expected response:
```json
{"status":"ok","message":"Server is running"}
```

### 2. List Current Images

```bash
curl http://localhost:3001/api/images
```

### 3. Upload Test Image (Windows PowerShell)

Create a test image first (or use an existing one), then:

```powershell
# Using Invoke-WebRequest in PowerShell
$filePath = "C:\path\to\your\image.png"
$uri = "http://localhost:3001/api/upload-image"

$fileContent = [System.IO.File]::ReadAllBytes($filePath)
$boundary = [System.Guid]::NewGuid().ToString()
$bodyLines = @(
    "--$boundary",
    "Content-Disposition: form-data; name=`"image`"; filename=`"test.png`"",
    "Content-Type: image/png",
    "",
    [System.Text.Encoding]::GetEncoding("iso-8859-1").GetString($fileContent),
    "--$boundary--"
) -join "`r`n"

Invoke-RestMethod -Uri $uri -Method Post -ContentType "multipart/form-data; boundary=$boundary" -Body $bodyLines
```

### 4. Update Example Image (Windows PowerShell)

```powershell
$filePath = "C:\path\to\your\image.png"
$uri = "http://localhost:3001/api/update-image/example1"

$fileContent = [System.IO.File]::ReadAllBytes($filePath)
$boundary = [System.Guid]::NewGuid().ToString()
$bodyLines = @(
    "--$boundary",
    "Content-Disposition: form-data; name=`"image`"; filename=`"test.png`"",
    "Content-Type: image/png",
    "",
    [System.Text.Encoding]::GetEncoding("iso-8859-1").GetString($fileContent),
    "--$boundary--"
) -join "`r`n"

Invoke-RestMethod -Uri $uri -Method Post -ContentType "multipart/form-data; boundary=$boundary" -Body $bodyLines
```

## Using Python

The easiest way to test on Windows is with Python:

```python
import requests

# Test 1: Health check
response = requests.get('http://localhost:3001/api/health')
print(response.json())

# Test 2: Upload image
with open('test.png', 'rb') as f:
    files = {'image': f}
    response = requests.post('http://localhost:3001/api/upload-image', files=files)
    print(response.json())

# Test 3: Update example1
with open('test.png', 'rb') as f:
    files = {'image': f}
    response = requests.post('http://localhost:3001/api/update-image/example1', files=files)
    print(response.json())
```

## Using curl (Git Bash or WSL)

If you have Git Bash or WSL on Windows:

```bash
# Health check
curl http://localhost:3001/api/health

# Upload image
curl -X POST http://localhost:3001/api/upload-image \
  -F "image=@test.png"

# Update example1
curl -X POST http://localhost:3001/api/update-image/example1 \
  -F "image=@test.png"
```

## Expected Workflow

1. Start the API server: `npm run server`
2. In another terminal, start the frontend: `npm run dev`
3. Open browser to http://localhost:5173
4. Use Python or curl to send images to the API
5. Watch the frontend automatically update with new images
