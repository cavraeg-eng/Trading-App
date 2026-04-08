---
name: image-enhancer
description: Enhances images and screenshots to make them sharper, clearer, and more professional. Use when improving image quality, upscaling images, sharpening blurry photos, reducing compression artifacts, or optimizing images for web, social media, presentations, or print.
---

# Image Enhancer

This skill takes your images and screenshots and makes them look better—sharper, clearer, and more professional.

## When to Use This Skill

- Improving screenshot quality for blog posts or documentation
- Enhancing images before sharing on social media
- Preparing images for presentations or reports
- Upscaling low-resolution images
- Sharpening blurry photos
- Cleaning up compressed images

## What This Skill Does

1. **Analyzes Image Quality**: Checks resolution, sharpness, and compression artifacts
2. **Enhances Resolution**: Upscales images intelligently
3. **Improves Sharpness**: Enhances edges and details
4. **Reduces Artifacts**: Cleans up compression artifacts and noise
5. **Optimizes for Use Case**: Adjusts based on intended use (web, print, social media)

## How to Use

### Basic Enhancement

```
Improve the image quality of screenshot.png
Enhance all images in this folder
```

### Specific Improvements

```
Upscale this image to 4K resolution
Sharpen this blurry screenshot
Reduce compression artifacts in this image
```

### Batch Processing

```
Improve the quality of all PNG files in this directory
```

## Enhancement Workflow

1. **Analyze the image**: Check current resolution, format, and quality issues
2. **Determine enhancements needed**: Based on user goals and image analysis
3. **Apply enhancements**: Use appropriate Python libraries (PIL/Pillow, opencv-python, etc.)
4. **Preserve original**: Always save original file as backup
5. **Report results**: Show what was improved and output file location

## Tools and Libraries

Use these Python libraries for image enhancement:

- **Pillow (PIL)**: Basic image operations, resizing, format conversion
- **opencv-python**: Advanced sharpening, denoising, edge enhancement
- **numpy**: Image array manipulation
- **scikit-image**: Advanced image processing algorithms

## Example Enhancement Output

```
Analyzing screenshot-2024.png...

Current specs:
- Resolution: 1920x1080
- Format: PNG
- Quality: Good, but slight blur

Enhancements applied:
✓ Upscaled to 2560x1440 (retina)
✓ Sharpened edges
✓ Enhanced text clarity
✓ Optimized file size

Saved as: screenshot-2024-enhanced.png
Original preserved as: screenshot-2024-original.png
```

## Tips

- Always keep original files as backup
- Works best with screenshots and digital images
- Can batch process entire folders
- Specify output format if needed (PNG for quality, JPG for smaller size)
- For social media, mention the platform for optimal sizing

## Common Use Cases

| Use Case | Recommended Settings |
|----------|---------------------|
| Blog Posts | Enhance screenshots before publishing |
| Documentation | Make UI screenshots crystal clear |
| Social Media | Optimize images for Twitter, LinkedIn, Instagram |
| Presentations | Upscale images for large screens |
| Print Materials | Increase resolution for physical media |

## Platform-Specific Sizes

- **Twitter/X**: 1200x675 (landscape), 1080x1080 (square)
- **LinkedIn**: 1200x627 (shared image), 1080x1350 (portrait)
- **Instagram**: 1080x1080 (square), 1080x1350 (portrait), 1080x566 (landscape)
