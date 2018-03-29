import requests
import re
from greent.service import Service
from greent.cache import Cache

class CachedService(Service):
    """ A service that caches requests. """
    def __init__(self, name, context):
        super(CachedService,self).__init__(name, context)
        self.punctuation = re.compile('[ ?=\./:{}]+')
    def get(self,url):
        print (f"url-------> {url}")
        print (f"url-------> {url}")
        print (f"url-------> {url}")
        print (f"url-------> {url}")
        print (f"url-------> {url}")
        print (f"url-------> {url}")
        key = self.punctuation.sub ('', url)            
        obj = self.context.cache.get(key)
        if not obj:
            obj = requests.get(url).json ()
            self.context.cache.set(key, obj)
        return obj
