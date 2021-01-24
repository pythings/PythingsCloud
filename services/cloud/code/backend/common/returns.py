
# Django imports
from rest_framework import status
from rest_framework.response import Response
from django.http import HttpResponse
import json


#==============================
#  Common returns
#==============================

# Ok (with data)
def ok200(caller=None, data=None):
    return Response({"status": "OK", "data": data}, status=status.HTTP_200_OK)

# Error 400
def error400(caller=None, error_msg=None):
    return Response({"status": "ERROR", "data": error_msg}, status=status.HTTP_400_BAD_REQUEST)

# Error 401
def error401(caller=None, error_msg=None):
    return Response({"status": "ERROR", "data": error_msg}, status=status.HTTP_401_UNAUTHORIZED)

# Error 404
def error404(caller=None, error_msg=None):
    return Response({"status": "ERROR", "data": error_msg}, status=status.HTTP_404_NOT_FOUND)

# Error 500
def error500(caller=None, error_msg=None):
    return Response({"status": "ERROR", "data": error_msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


#========================================
#  Common returns (more REST-compliant)
#========================================

# Ok (with data)
def ok200rest(caller=None, data=None):
    return Response(data, status=status.HTTP_200_OK)

# Error 400
def error400rest(caller=None, error_msg=None):
    return Response({'detail': error_msg}, status=status.HTTP_400_BAD_REQUEST)

# Error 401
def error401rest(caller=None, error_msg=None):
    return Response({'detail': error_msg}, status=status.HTTP_401_UNAUTHORIZED)

# Error 404
def error404rest(caller=None, error_msg=None):
    return Response({'detail': error_msg}, status=status.HTTP_404_NOT_FOUND)

# Error 500
def error500rest(caller=None, error_msg=None):
    return Response({'detail': error_msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


#===========================================
# Thing common returns (encryption support)
#===========================================

def response(payload, status=None, caller=None, raw=False):
    #logger.debug(' ** OUT ** - Preparing payload {}'.format(payload))
    if caller and caller.payload_encrypter:
        payload_encrypter = caller.payload_encrypter
    else:
        payload_encrypter = None
    
    if payload_encrypter:
        
        if raw:     
            # Payload must be string
            payload = payload_encrypter.encrypt_text(str(payload))
            #logger.debug(' ** OUT ** - Returning encypted payload: {}'.format(payload))
            return HttpResponse(payload, status=status)
        else:
            # Payload must be JSON-serializable object
            payload = payload_encrypter.encrypt_text(json.dumps(payload))
            #logger.debug(' ** OUT ** - Returning encypted payload: {}'.format(payload))
            return HttpResponse(payload, status=status)

    else:
        
        # If it was explicitlt asked to return RAW do so, otherwise return JSON-encoded
        if raw:
            #logger.info(' ** OUT ** - Returning not encypted raw payload: {}'.format(payload))
            return HttpResponse(payload, status=status)
        else:
            return Response(payload, status=status)

# Ok (with data)
def ok200thing(caller=None, data=None, raw=False):
    if raw:
        return response(data, status.HTTP_200_OK, caller, raw=True)
    else:
        return response(data, status.HTTP_200_OK, caller)

# Error 400
def error400thing(caller=None, error_msg=None):
    return response(error_msg, status.HTTP_400_BAD_REQUEST, caller)

# Error 401
def error401thing(caller=None, error_msg=None):
    return response(error_msg, status.HTTP_401_UNAUTHORIZED, caller)

# Error 404
def error404thing(caller=None, error_msg=None):
    return response(error_msg, status.HTTP_404_NOT_FOUND, caller)

# Error 500
def error500thing(caller=None, error_msg=None):
    return response(error_msg, status.HTTP_500_INTERNAL_SERVER_ERROR, caller)
