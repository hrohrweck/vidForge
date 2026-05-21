"""
VidForge Plugin System.

Templates are self-contained plugins that define their own pipeline stages,
scene planning, and UI schema.  The core system provides shared services
(image generation, video generation, LLM, rendering) and calls plugin
methods at each stage of the job lifecycle.
"""
