"""ŠkodaCAD – osobní parametrický 3D CAD nad build123d / Open CASCADE.

Model dílu je čitelný JSON „recept“ (parametry + seznam prvků). Jádro
z něj kdykoli znovu postaví přesné B-rep těleso.
"""

from skodacad.document import Document, DocumentError
from skodacad.rebuild import BuildResult, FeatureStatus, rebuild

__all__ = ["BuildResult", "Document", "DocumentError", "FeatureStatus", "rebuild"]
__version__ = "0.1.0"
