// Cesium's workers, widgets and runtime assets must be served alongside its script.
import { cpSync, mkdirSync } from 'node:fs';
mkdirSync('public/cesium', { recursive: true });
cpSync('node_modules/cesium/Build/Cesium', 'public/cesium', { recursive: true });
